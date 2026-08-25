"""The Briefing Desk ranker must put relevance ahead of recency.

The compose flow used to sort candidates by publication date with the alignment
floor disabled, so the newest row won whatever it was about. On wileytest that
put three Bluesky posts about a city council election, each scored 0.00 against
"Brand Monitoring Pearsons Education", at the top of the list the curator saw,
while 21 articles scoring 0.7+ under "Brand Monitoring Wiley" never appeared.

These tests hold the replacement to that: alignment dominates, recency is a
bounded tie-breaker, every requested topic gets shortlist exposure, syndicated
copies collapse to one candidate, and a source cap defers rather than discards.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.daily_briefing_ranking import (
    MAX_PER_SOURCE,
    SOURCE_CAP_OVERRIDE_GAP,
    annotate_candidates,
    backfill,
    build_shortlist,
    clamp01,
    credibility_score,
    dedupe_candidates,
    normalize_score,
    normalize_title,
    normalize_uri,
    parse_publication_time,
    rank,
    recency_score,
    score_article,
    title_similarity,
)

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def article(uri, *, align=0.8, days_ago=0.5, source="example.com", title=None, **extra):
    row = {
        "uri": uri,
        "title": title or f"Story {uri}",
        "summary": "summary",
        "publication_date": _iso(days_ago),
        "news_source": source,
        "topic_alignment_score": align,
    }
    row.update(extra)
    return row


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

class TestNormalization:
    @pytest.mark.parametrize("raw,expected", [
        (0.85, 0.85), ("0.5", 0.5), (85, 0.85), (None, None),
        ("", None), ("abc", None), (-2, 0.0), (True, None),
    ])
    def test_normalize_score(self, raw, expected):
        assert normalize_score(raw) == expected

    def test_clamp(self):
        assert clamp01(1.7) == 1.0 and clamp01(-0.2) == 0.0

    @pytest.mark.parametrize("raw", [
        "2026-08-19T09:00:00", "2026-08-19T09:00:00+00:00",
        "2026-08-19T09:00:00Z", "2026-08-19",
    ])
    def test_parse_publication_time_accepts_stored_shapes(self, raw):
        assert parse_publication_time(raw) is not None

    @pytest.mark.parametrize("raw", [None, "", "not a date", "19/08/2026"])
    def test_unparseable_dates_return_none(self, raw):
        assert parse_publication_time(raw) is None

    def test_missing_date_gets_no_freshness_credit(self):
        assert recency_score(None, NOW) == 0.0

    def test_recency_halves_at_the_half_life(self):
        assert recency_score(NOW - timedelta(days=3), NOW) == pytest.approx(0.5, abs=1e-6)

    def test_future_dates_do_not_exceed_one(self):
        assert recency_score(NOW + timedelta(days=2), NOW) == 1.0

    def test_credibility_lookup_and_unknown_is_zero_contribution(self):
        assert credibility_score({"mbfc_credibility_rating": "high credibility"}) == 1.0
        assert credibility_score({"factual_reporting": "mixed"}) == 0.5
        assert credibility_score({"mbfc_credibility_rating": "wat"}) is None

    def test_credibility_takes_the_better_of_the_two_fields(self):
        row = {"mbfc_credibility_rating": "low credibility", "factual_reporting": "high"}
        assert credibility_score(row) == 1.0

    def test_uri_normalization_strips_tracking(self):
        a = normalize_uri("https://www.fastcompany.com/91589122/x?partner=rss&utm_source=rss")
        b = normalize_uri("http://fastcompany.com/91589122/x/")
        assert a == b == "fastcompany.com/91589122/x"

    def test_title_normalization_drops_the_appended_source_and_date(self):
        assert normalize_title("NIH Holds Grants (joemygod.com, 2026-08-17)") == "nih holds grants"


# --------------------------------------------------------------------------
# Relevance versus recency
# --------------------------------------------------------------------------

class TestRelevanceBeatsRecency:
    def test_yesterdays_strong_article_outranks_todays_weak_one(self):
        strong = article("s", align=0.95, days_ago=1)
        weak = article("w", align=0.10, days_ago=0)
        ordered = rank(annotate_candidates([weak, strong], topic="t", now=NOW))
        assert ordered[0]["uri"] == "s"

    def test_a_social_post_scored_zero_cannot_lead_on_freshness_alone(self):
        """The exact shape of the failure: a 0.00-alignment post minutes old
        against a 0.84-alignment article from yesterday."""
        post = article("post", align=0.0, days_ago=0.01,
                       source="bluesky", title="Post by @sjpete.bsky.social")
        news = article("news", align=0.84, days_ago=1.2, source="business-standard.com")
        ordered = rank(annotate_candidates([post, news], topic="t", now=NOW))
        assert [r["uri"] for r in ordered] == ["news", "post"]

    def test_recency_only_breaks_ties_between_equivalent_candidates(self):
        older = article("older", align=0.8, days_ago=2)
        newer = article("newer", align=0.8, days_ago=0.5)
        ordered = rank(annotate_candidates([older, newer], topic="t", now=NOW))
        assert [r["uri"] for r in ordered] == ["newer", "older"]

    def test_recency_cannot_outweigh_a_large_alignment_gap(self):
        """Recency is worth 0.10 at most; a 0.5 alignment gap is worth 0.25."""
        fresh_weak = score_article(article("a", align=0.40, days_ago=0), now=NOW)["composite"]
        stale_strong = score_article(article("b", align=0.90, days_ago=10), now=NOW)["composite"]
        assert stale_strong > fresh_weak

    def test_a_missing_date_does_not_crash_or_win(self):
        dated = article("dated", align=0.8, days_ago=1)
        undated = article("undated", align=0.8)
        undated["publication_date"] = "gibberish"
        ordered = rank(annotate_candidates([undated, dated], topic="t", now=NOW))
        assert ordered[0]["uri"] == "dated"

    def test_missing_optional_signals_contribute_zero_not_a_neutral_value(self):
        bare = score_article(article("a", align=1.0, days_ago=99), now=NOW)
        assert bare["composite"] == pytest.approx(0.50, abs=1e-3)

    def test_user_preference_is_a_small_bounded_adjustment(self):
        base = score_article(article("a", align=0.8, days_ago=1), now=NOW)["composite"]
        more = score_article(article("a", align=0.8, days_ago=1, user_preference="more"), now=NOW)["composite"]
        less = score_article(article("a", align=0.8, days_ago=1, user_preference="less"), now=NOW)["composite"]
        assert less < base < more
        assert more - base == pytest.approx(0.05, abs=1e-6)

    def test_preference_cannot_lift_an_off_topic_article_over_a_strong_one(self):
        off = article("off", align=0.05, days_ago=0, user_preference="more")
        on = article("on", align=0.90, days_ago=1)
        ordered = rank(annotate_candidates([off, on], topic="t", now=NOW))
        assert ordered[0]["uri"] == "on"

    def test_ordering_is_total_and_repeatable(self):
        rows = [article(f"u{i}", align=0.8, days_ago=1) for i in range(6)]
        first = [r["uri"] for r in rank(annotate_candidates(rows, topic="t", now=NOW))]
        second = [r["uri"] for r in rank(annotate_candidates(list(reversed(rows)), topic="t", now=NOW))]
        assert first == second


# --------------------------------------------------------------------------
# Deduplication
# --------------------------------------------------------------------------

class TestDeduplication:
    def test_exact_uri_duplicates_collapse(self):
        rows = annotate_candidates([article("https://x.com/a"), article("https://x.com/a")],
                                   topic="t", now=NOW)
        kept, dropped = dedupe_candidates(rows)
        assert len(kept) == 1 and dropped == 1

    def test_tracking_parameters_do_not_create_a_second_candidate(self):
        a = article("https://fastcompany.com/9158/ai?partner=rss&utm_source=rss")
        b = article("https://www.fastcompany.com/9158/ai")
        kept, dropped = dedupe_candidates(annotate_candidates([a, b], topic="t", now=NOW))
        assert len(kept) == 1 and dropped == 1

    def test_syndicated_copies_keep_the_higher_ranked_representative(self):
        title = "NTT DOCOMO Deploys Second D-Wave Production Quantum Application for Network"
        weak = article("https://aggregator.com/1", align=0.70, title=title, source="aggregator.com")
        strong = article("https://thequantuminsider.com/1", align=0.90, title=title,
                         source="thequantuminsider.com")
        kept, dropped = dedupe_candidates(annotate_candidates([weak, strong], topic="t", now=NOW))
        assert dropped == 1
        assert kept[0]["news_source"] == "thequantuminsider.com"

    def test_near_identical_retitled_copies_merge(self):
        a = article("https://kmworld.com/1",
                    title="Concentric AI unveils new feature for sensitive data discovery in cloud")
        b = article("https://businesswire.com/1",
                    title="Concentric AI's new feature expands sensitive data discovery in cloud")
        kept, dropped = dedupe_candidates(annotate_candidates([a, b], topic="t", now=NOW))
        assert len(kept) == 1 and dropped == 1

    def test_distinct_developments_sharing_generic_words_are_not_merged(self):
        a = article("https://x.com/1", title="Ukraine launches major drone blitz against Russian refinery")
        b = article("https://y.com/1", title="Russia launches missile strike against Ukrainian power grid")
        kept, _ = dedupe_candidates(annotate_candidates([a, b], topic="t", now=NOW))
        assert len(kept) == 2

    def test_short_titles_are_never_merged_by_similarity(self):
        a = article("https://x.com/1", title="Wiley results")
        b = article("https://y.com/1", title="Wiley update")
        kept, _ = dedupe_candidates(annotate_candidates([a, b], topic="t", now=NOW))
        assert len(kept) == 2

    def test_a_merged_duplicate_keeps_every_topic_it_matched(self):
        """First-seen topic iteration used to decide the stored topic, so the
        second topic's claim on the article vanished."""
        rows = (annotate_candidates([article("https://x.com/a")], topic="Patent Cliffs", now=NOW)
                + annotate_candidates([article("https://x.com/a")], topic="M&A Updates", now=NOW))
        kept, _ = dedupe_candidates(rows)
        assert len(kept) == 1
        assert set(kept[0]["_topics"]) == {"Patent Cliffs", "M&A Updates"}

    def test_similarity_is_zero_for_titles_below_the_token_floor(self):
        assert title_similarity("Wiley up", "Wiley down") == 0.0

    def test_a_short_title_swallowed_by_a_long_one_is_not_merged(self):
        short = "NIH holds up hundreds of research grants"
        long = ("NIH holds up hundreds of research grants as agency leadership turmoil "
                "deepens and universities warn of layoffs across dozens of medical schools")
        assert title_similarity(short, long) == 0.0

    def test_same_entity_different_development_is_not_merged(self):
        a = article("https://x.com/1",
                    title="IonQ collaborates with CMC Microsystems to expand cloud quantum access")
        b = article("https://y.com/1",
                    title="IonQ collaborates with university partners to expand quantum research")
        kept, _ = dedupe_candidates(annotate_candidates([a, b], topic="t", now=NOW))
        assert len(kept) == 2


# --------------------------------------------------------------------------
# Shortlist balance and source diversity
# --------------------------------------------------------------------------

class TestShortlist:
    def _by_topic(self, spec):
        return {t: rank(annotate_candidates(rows, topic=t, now=NOW)) for t, rows in spec.items()}

    def test_every_topic_is_represented_before_any_topic_repeats(self):
        by_topic = self._by_topic({
            "busy": [article(f"busy{i}", align=0.9, source=f"s{i}.com") for i in range(20)],
            "quiet": [article("quiet1", align=0.8, source="q.com")],
            "sparse": [article("sparse1", align=0.75, source="p.com")],
        })
        shortlist, stats = build_shortlist(by_topic, limit=6, topic_order=["busy", "quiet", "sparse"])
        assert stats["per_topic"]["quiet"] == 1
        assert stats["per_topic"]["sparse"] == 1
        assert [r["uri"] for r in shortlist[:3]] == ["busy0", "quiet1", "sparse1"]

    def test_a_high_volume_topic_cannot_take_every_slot(self):
        """Three topics with eligible material, 30 slots, one topic holding 100
        candidates: the old global sort gave that topic all 30."""
        by_topic = self._by_topic({
            "flood": [article(f"f{i}", align=0.9, days_ago=0.01, source=f"f{i}.com") for i in range(100)],
            "b": [article(f"b{i}", align=0.85, days_ago=3, source=f"b{i}.com") for i in range(5)],
            "c": [article(f"c{i}", align=0.85, days_ago=3, source=f"c{i}.com") for i in range(5)],
        })
        _, stats = build_shortlist(by_topic, limit=30, topic_order=["flood", "b", "c"])
        assert stats["per_topic"]["b"] == 5
        assert stats["per_topic"]["c"] == 5
        assert stats["per_topic"]["flood"] == 20

    def test_a_strong_candidate_past_position_thirty_reaches_the_shortlist(self):
        """A weak topic's best article used to sit behind 30 fresher, weaker
        rows from a busy topic and never be seen."""
        by_topic = self._by_topic({
            "busy": [article(f"n{i}", align=0.45, days_ago=0.01, source=f"n{i}.com") for i in range(40)],
            "buried": [article("gem", align=0.95, days_ago=2, source="gem.com")],
        })
        shortlist, _ = build_shortlist(by_topic, limit=30, topic_order=["busy", "buried"])
        assert "gem" in [r["uri"] for r in shortlist]
        assert shortlist.index(next(r for r in shortlist if r["uri"] == "gem")) == 1

    def test_a_source_beyond_the_cap_is_deferred_not_discarded(self):
        """Four articles from one outlet, nothing else to fill with: the fourth
        must still make the shortlist rather than being dropped at gather time."""
        by_topic = self._by_topic({
            "t": [article(f"h{i}", align=0.9 - i * 0.01, source="hub.com") for i in range(4)],
        })
        shortlist, stats = build_shortlist(by_topic, limit=8, topic_order=["t"])
        assert len(shortlist) == 4
        assert stats["deferred_for_source"] >= 1
        assert stats["second_pass"] >= 1

    def test_the_cap_still_bites_when_alternatives_exist(self):
        by_topic = self._by_topic({
            "t": ([article(f"h{i}", align=0.9, source="hub.com") for i in range(5)]
                  + [article(f"o{i}", align=0.85, source=f"o{i}.com") for i in range(5)]),
        })
        shortlist, _ = build_shortlist(by_topic, limit=5, topic_order=["t"])
        hub = [r for r in shortlist if r["news_source"] == "hub.com"]
        assert len(hub) == MAX_PER_SOURCE

    def test_a_fourth_excellent_article_survives_three_weak_ones_from_that_source(self):
        """The old early cap kept whichever three arrived first in date order."""
        rows = [article(f"weak{i}", align=0.45, days_ago=0.01, source="hub.com") for i in range(3)]
        rows.append(article("excellent", align=0.98, days_ago=2, source="hub.com"))
        shortlist, _ = build_shortlist(self._by_topic({"t": rows}), limit=8, topic_order=["t"])
        assert "excellent" in [r["uri"] for r in shortlist]

    def test_shortlist_is_deterministic(self):
        spec = {"a": [article(f"a{i}", align=0.8, source=f"s{i}.com") for i in range(10)],
                "b": [article(f"b{i}", align=0.8, source=f"t{i}.com") for i in range(10)]}
        one, _ = build_shortlist(self._by_topic(spec), limit=7, topic_order=["a", "b"])
        two, _ = build_shortlist(self._by_topic(spec), limit=7, topic_order=["a", "b"])
        assert [r["uri"] for r in one] == [r["uri"] for r in two]


# --------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------

class TestBackfill:
    def test_it_fills_to_target_from_the_best_remaining(self):
        pool = rank(annotate_candidates(
            [article(f"p{i}", align=0.9 - i * 0.05, source=f"s{i}.com") for i in range(8)],
            topic="t", now=NOW))
        selected = pool[:3]
        added = backfill(selected, pool, target=8)
        assert len(added) == 5
        assert [r["uri"] for r in added] == ["p3", "p4", "p5", "p6", "p7"]

    def test_it_never_re_adds_something_already_selected(self):
        pool = rank(annotate_candidates(
            [article(f"p{i}", align=0.9) for i in range(4)], topic="t", now=NOW))
        added = backfill(pool[:2], pool, target=8)
        assert not ({r["uri"] for r in added} & {r["uri"] for r in pool[:2]})

    def test_it_stops_short_when_the_pool_runs_out(self):
        pool = rank(annotate_candidates(
            [article(f"p{i}", align=0.9, source=f"s{i}.com") for i in range(3)], topic="t", now=NOW))
        assert len(backfill(pool[:1], pool, target=8)) == 2

    def test_it_covers_every_topic_before_deepening_one(self):
        """Eight slots and three topics: each topic must be represented, even
        though the busiest topic holds the eight highest-scoring candidates."""
        busy = annotate_candidates(
            [article(f"busy{i}", align=0.95, source=f"s{i}.com") for i in range(8)],
            topic="Busy", now=NOW)
        quiet = annotate_candidates([article("quiet", align=0.60, source="q.com")],
                                    topic="Quiet", now=NOW)
        sparse = annotate_candidates([article("sparse", align=0.55, source="p.com")],
                                     topic="Sparse", now=NOW)
        pool = rank(busy + quiet + sparse)
        added = backfill([], pool, target=8, topics=["Busy", "Quiet", "Sparse"])
        covered = {t for r in added for t in r["_topics"]}
        assert covered == {"Busy", "Quiet", "Sparse"}
        assert len(added) == 8

    def test_topic_coverage_is_skipped_when_there_are_more_topics_than_slots(self):
        rows = []
        for i in range(20):
            rows += annotate_candidates(
                [article(f"t{i}", align=0.9 - i * 0.01, source=f"s{i}.com")],
                topic=f"Topic{i}", now=NOW)
        added = backfill([], rank(rows), target=8, topics=[f"Topic{i}" for i in range(20)])
        assert [r["uri"] for r in added] == [f"t{i}" for i in range(8)]

    def test_source_diversity_holds_when_alternatives_are_comparable(self):
        rows = ([article(f"h{i}", align=0.90, source="hub.com") for i in range(6)]
                + [article(f"o{i}", align=0.86, source=f"o{i}.com") for i in range(6)])
        pool = rank(annotate_candidates(rows, topic="t", now=NOW))
        added = backfill([], pool, target=8)
        assert len([r for r in added if r["news_source"] == "hub.com"]) == MAX_PER_SOURCE

    def test_the_cap_yields_when_the_alternative_is_materially_weaker(self):
        """Documented override: a gap wider than SOURCE_CAP_OVERRIDE_GAP means
        diversity would be costing the briefing a much better story."""
        rows = ([article(f"h{i}", align=0.95, source="hub.com") for i in range(5)]
                + [article("thin", align=0.05, source="thin.com")])
        pool = rank(annotate_candidates(rows, topic="t", now=NOW))
        added = backfill([], pool, target=4)
        gap = pool[0]["_score"] - next(r for r in pool if r["uri"] == "thin")["_score"]
        assert gap > SOURCE_CAP_OVERRIDE_GAP
        assert len([r for r in added if r["news_source"] == "hub.com"]) == 4
