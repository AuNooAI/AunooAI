"""Identity resolution, observations and field merging at insert
(app/services/article_identity.py; story_identity.story_url_key).

No database: a fake facade answers the SQL the module sends from a dict of
stored rows, and records every write. Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md,
work packages 4, 8 and 30.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import article_identity as ai
from app.services import story_identity as si


# ---------------------------------------------------------------------------
# A. story_url_key uses the registry
# ---------------------------------------------------------------------------

SA = "https://seekingalpha.com/news/4647846-volkswagen-and-gotion-high-tech-to-invest-322b"
SM = "https://www.streamingmedia.com/Articles/News/Online-Video-News/x.aspx"


def test_seekingalpha_variants_share_one_key():
    assert si.story_url_key(SA + "?feed_item_type=news") == si.story_url_key(SA)
    assert si.story_url_key(SA + "?source=feed&feed_item_type=news") == si.story_url_key(SA)


def test_streamingmedia_article_ids_are_two_keys():
    assert si.story_url_key(SM + "?ArticleID=1") != si.story_url_key(SM + "?ArticleID=2")


def test_bbc_and_zacks_host_parameters_come_from_the_registry():
    bbc = "https://www.bbc.co.uk/news/articles/c1"
    assert si.story_url_key(bbc + "?at_medium=RSS&at_campaign=rss") == si.story_url_key(bbc)
    zacks = "https://www.zacks.com/stock/news/2997217/vw-taps-gotion"
    assert si.story_url_key(zacks + "?cid=CS-ZC-FT") == si.story_url_key(zacks)
    # cid is only tracking on zacks: elsewhere it may identify the page.
    other = "https://example.com/page"
    assert si.story_url_key(other + "?cid=1") != si.story_url_key(other + "?cid=2")


def test_kept_query_keeps_its_encoding():
    # url_key is compared as stored text, so a kept value must not be re-encoded.
    assert si.story_url_key("https://example.com/s?q=a%20b&utm_source=x") == "example.com/s?q=a%20b"


# ---------------------------------------------------------------------------
# Fake facade
# ---------------------------------------------------------------------------

class FakeFacade:
    """Answers the module's lookups from ``rows`` and keeps every write."""

    def __init__(self, rows=(), aliases=None, observations=None):
        self.rows = {r["uri"]: dict(r) for r in rows}
        self.aliases = dict(aliases or {})            # url -> article_uri
        self.observations = dict(observations or {})  # observation_key -> article_uri
        self.writes = []

    def _fetchone_with_rollback(self, stmt, params=None, operation_name="query", mappings=False):
        sql = str(stmt)
        p = params or {}
        if "FROM articles WHERE uri = :uri" in sql:
            return (p["uri"],) if p["uri"] in self.rows else None
        if "FROM article_observations" in sql:
            uri = self.observations.get(p["k"])
            return (uri,) if uri else None
        if "social_meta->>'platform'" in sql:
            for r in self.rows.values():
                m = r.get("social_meta") or {}
                if m.get("platform") == p["p"] and str(m.get("external_id")) == p["e"]:
                    return (r["uri"],)
            return None
        if "FROM article_url_aliases" in sql:
            for u in (p["u"], p["c"]):
                if u in self.aliases:
                    return (self.aliases[u],)
            return None
        if "WHERE canonical_url = :c" in sql:
            hits = [r for r in self.rows.values() if r.get("canonical_url") == p["c"]]
            hits.sort(key=lambda r: r.get("topic") != p["topic"])
            return (hits[0]["uri"],) if hits else None
        if "WHERE url_key = :k" in sql:
            hits = [r for r in self.rows.values() if r.get("url_key") == p["k"]]
            hits.sort(key=lambda r: r.get("topic") != p["topic"])
            return (hits[0]["uri"],) if hits else None
        raise AssertionError(f"unexpected lookup: {sql}")

    def _execute_with_rollback(self, stmt, params=None, operation_name="query"):
        sql = str(stmt)
        p = params or {}
        self.writes.append((sql, p))
        if "INSERT INTO article_url_aliases" in sql:
            self.aliases.setdefault(p["url"], p["uri"])
        elif "INSERT INTO article_observations" in sql:
            self.observations.setdefault(p["key"], p["uri"])


NEWS_ROW = {
    "uri": SA, "topic": "European Battery Industry", "title": "VW and Gotion to invest 3.22B",
    "summary": "Short excerpt...", "publication_date": "2026-09-29T07:00:00+00:00",
    "canonical_url": SA, "url_key": si.story_url_key(SA), "content_kind": "excerpt",
}


# ---------------------------------------------------------------------------
# B. resolve_identity
# ---------------------------------------------------------------------------

def test_exact_uri_is_found_first():
    res = ai.resolve_identity(FakeFacade([NEWS_ROW]), {"url": SA, "title": "x"})
    assert res.existing and res.uri == SA and res.matched_by == ai.MATCH_URI
    assert res.method == "canonical_url"


def test_alias_lookup_finds_the_row_for_a_tracking_variant():
    fac = FakeFacade([NEWS_ROW], aliases={SA + "?feed_item_type=news": SA})
    res = ai.resolve_identity(fac, {"url": SA + "?feed_item_type=news", "title": "x"})
    assert res.existing and res.uri == SA and res.matched_by == ai.MATCH_ALIAS


def test_canonical_url_lookup_finds_the_row_for_a_new_variant():
    # No alias yet: the variant canonicalises to the stored canonical_url.
    fac = FakeFacade([NEWS_ROW])
    res = ai.resolve_identity(fac, {"url": SA + "?utm_source=rss&feed_item_type=news"})
    assert res.existing and res.uri == SA and res.matched_by == ai.MATCH_CANONICAL
    assert res.canonical_url == SA


def test_url_key_lookup_is_the_last_resort():
    row = dict(NEWS_ROW, canonical_url=None)
    res = ai.resolve_identity(FakeFacade([row]), {"url": SA + "?feed_item_type=news"})
    assert res.existing and res.uri == SA and res.matched_by == ai.MATCH_URL_KEY


def test_functional_query_parameter_keeps_two_resources_distinct():
    row = dict(NEWS_ROW, uri=SM + "?ArticleID=1", canonical_url=SM + "?ArticleID=1",
               url_key=si.story_url_key(SM + "?ArticleID=1"))
    res = ai.resolve_identity(FakeFacade([row]), {"url": SM + "?ArticleID=2"})
    assert not res.existing and res.uri is None


def test_social_identity_beats_the_url():
    post = {"url": "https://www.instagram.com/oviva/", "title": "a post",
            "social_meta": {"platform": "instagram", "external_id": "111"},
            "raw_data": {"platform": "instagram", "external_id": "111", "provider": "xpoz"}}
    res = ai.resolve_identity(FakeFacade(), post)
    assert res.record_type == "social_post"
    assert res.method == "platform_post_id" and res.identity_key == "instagram:111"


def test_two_instagram_posts_sharing_a_profile_url_stay_two_rows():
    first = {"uri": "xpoz://instagram/111", "topic": "T", "title": "first post",
             "canonical_url": "https://www.instagram.com/oviva/",
             "url_key": si.story_url_key("https://www.instagram.com/oviva/"),
             "social_meta": {"platform": "instagram", "external_id": "111"}}
    fac = FakeFacade([first], aliases={"https://www.instagram.com/oviva/": "xpoz://instagram/111"})
    second = {"url": "https://www.instagram.com/oviva/", "uri": "xpoz://instagram/222", "title": "second post",
              "social_meta": {"platform": "instagram", "external_id": "222"},
              "raw_data": {"platform": "instagram", "external_id": "222", "provider": "xpoz"}}
    res = ai.resolve_identity(fac, second)
    assert not res.existing, "a shared profile URL must not merge two posts"


def test_same_social_post_under_a_second_url_is_the_existing_row():
    row = {"uri": "https://x.com/acme/status/5", "topic": "T", "title": "tweet",
           "social_meta": {"platform": "twitter", "external_id": "5"}}
    fac = FakeFacade([row])
    res = ai.resolve_identity(fac, {"url": "https://twitter.com/i/status/5", "title": "tweet",
                                    "social_meta": {"platform": "twitter", "external_id": "5"},
                                    "raw_data": {"platform": "twitter", "external_id": "5", "provider": "xpoz"}})
    assert res.existing and res.uri == "https://x.com/acme/status/5"
    assert res.matched_by == ai.MATCH_SOCIAL_META


def test_scholarly_record_is_identified_by_doi():
    res = ai.resolve_identity(FakeFacade(), {"url": "https://arxiv.org/abs/2401.00001",
                                             "raw_data": {"arxiv_id": "2401.00001", "doi": "10.1000/ABC.1"}})
    assert res.record_type == "scholarly" and res.method == "doi" and res.identity_key == "10.1000/abc.1"


def test_lookup_failures_never_raise():
    class Broken(FakeFacade):
        def _fetchone_with_rollback(self, *a, **k):
            raise RuntimeError("db down")
    res = ai.resolve_identity(Broken(), {"url": SA})
    assert not res.existing and res.canonical_url == SA


# ---------------------------------------------------------------------------
# B. record_observation
# ---------------------------------------------------------------------------

def test_observation_and_alias_are_written_with_the_registry_version():
    fac = FakeFacade([NEWS_ROW])
    art = {"url": SA + "?feed_item_type=news", "title": "x", "source": "seekingalpha.com",
           "published_date": "2026-09-29T07:05:00+00:00", "authors": ["A. Writer"]}
    assert ai.record_observation(fac, SA, art, "seekingalpha.com") is True
    kinds = [w[0].split("(")[0].strip() for w in fac.writes]
    assert any("INSERT INTO article_observations" in k for k in kinds)
    alias = next(p for s, p in fac.writes if "article_url_aliases" in s)
    assert alias["url"] == SA + "?feed_item_type=news" and alias["canonical"] == SA
    assert alias["version"] and alias["uri"] == SA
    upd = next(p for s, p in fac.writes if "UPDATE articles SET canonical_url" in s)
    assert upd["uri"] == SA and upd["method"] == "canonical_url"
    obs = next(p for s, p in fac.writes if "article_observations" in s)
    assert '"authors": ["A. Writer"]' in obs["payload"]


def test_observation_write_failure_is_reported_not_raised():
    class Broken(FakeFacade):
        def _execute_with_rollback(self, *a, **k):
            raise RuntimeError("db down")
    assert ai.record_observation(Broken(), SA, {"url": SA}, "newsapi") is False


# ---------------------------------------------------------------------------
# B. merge_fields
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_nonempty_is_never_replaced_by_empty():
    row = {"title": "Kept", "summary": "Kept body", "news_source": "a.com",
           "publication_date": "2026-09-29", "content_kind": "full_text"}
    up = ai.merge_fields(row, {"title": "", "summary": "", "source": None, "published_date": ""}, now=NOW)
    assert set(up) == {"last_seen_at"}


def test_empty_columns_are_filled():
    row = {"title": "", "summary": None, "news_source": None, "publication_date": None}
    up = ai.merge_fields(row, {"title": "New", "summary": "Body", "source": "b.com",
                               "published_date": "2026-09-29", "publication_date_precision": "day"}, now=NOW)
    assert up["title"] == "New" and up["summary"] == "Body" and up["news_source"] == "b.com"
    assert up["publication_date"] == "2026-09-29" and up["publication_date_precision"] == "day"
    assert up["content_kind"] == "excerpt"


def test_full_text_beats_an_excerpt_but_not_the_other_way():
    row = {"summary": "Short excerpt of the story", "content_kind": "excerpt", "publication_date": "2026-09-29"}
    up = ai.merge_fields(row, {"content": "The whole story, " * 20, "content_kind": "full_text"}, now=NOW)
    assert up["summary"].startswith("The whole story") and up["content_kind"] == "full_text"
    # An excerpt never replaces a stored full text, however long it is.
    row2 = {"summary": "Full text here", "content_kind": "full_text"}
    up2 = ai.merge_fields(row2, {"summary": "A much longer excerpt " * 10, "content_kind": "excerpt"}, now=NOW)
    assert "summary" not in up2
    # A longer excerpt only replaces an excerpt the provider cut off.
    row3 = {"summary": "Cut off here [+1234 chars]", "content_kind": "excerpt"}
    up3 = ai.merge_fields(row3, {"summary": "Cut off here and then the rest of the paragraph."}, now=NOW)
    assert up3["summary"].endswith("paragraph.")
    row4 = {"summary": "Complete short excerpt.", "content_kind": "excerpt"}
    up4 = ai.merge_fields(row4, {"summary": "Complete short excerpt. Plus more words from elsewhere."}, now=NOW)
    assert "summary" not in up4


def test_conflicting_known_date_is_not_overwritten():
    row = {"publication_date": "2026-09-29T07:00:00+00:00", "summary": "x"}
    up = ai.merge_fields(row, {"published_date": "2026-09-30T07:00:00+00:00"}, now=NOW)
    assert "publication_date" not in up
    assert up["_date_conflict"]["incoming"] == "2026-09-30T07:00:00+00:00"
    assert "publication_date" not in ai.column_updates(up)
    # The same instant in another shape is not a conflict.
    up2 = ai.merge_fields({"publication_date": "2026-09-29"}, {"published_date": "2026-09-29T00:00:00Z"}, now=NOW)
    assert "_date_conflict" not in up2


def test_protected_columns_are_never_produced():
    row = {"first_seen_at": "old", "submission_date": "old", "category": "AI", "summary": "x"}
    up = ai.merge_fields(row, {"first_seen_at": "new", "submission_date": "new", "category": "Other",
                               "sentiment": "positive"}, now=NOW)
    assert not (set(up) & ai.PROTECTED_COLUMNS)
    assert up["last_seen_at"] == NOW


def test_authors_are_unioned_when_the_row_has_the_column():
    up = ai.merge_fields({"authors": ["A"], "summary": "x"}, {"authors": ["A", "B"]}, now=NOW)
    assert up["authors"] == ["A", "B"]
    # The monolith articles table has no authors column: nothing to write.
    up2 = ai.merge_fields({"summary": "x"}, {"authors": ["A", "B"]}, now=NOW)
    assert "authors" not in up2


def test_record_type_and_provider_helpers():
    assert ai.record_type_of({"social_meta": {"platform": "bluesky"}}) == "social_post"
    assert ai.record_type_of({"raw_data": {"platform": "reddit"}}) == "social_post"
    assert ai.record_type_of({"raw_data": {"arxiv_id": "1"}}) == "scholarly"
    assert ai.record_type_of({"url": "https://a.com"}) == "news"
    assert ai.provider_of({"source": "xpoz:instagram"}) == "xpoz"
    assert ai.provider_of({"raw_data": {"provider": "NewsAPI"}}) == "newsapi"
    assert ai.content_kind_of({"social_meta": {"platform": "x"}}) == "social_post"
    assert ai.content_kind_of({"content_kind": "full_text"}) == "full_text"
    assert ai.content_kind_of({}) == "excerpt"
