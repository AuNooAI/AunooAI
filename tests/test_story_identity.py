"""Copy and press-release labels (app/services/story_identity.py).

Fixtures are the four cases that reached the "European Battery Industry"
topic on 1 October 2026. No database: label_article runs against a fake
facade that answers the two queries it makes.
"""
from app.services import story_identity as si
from app.services.article_visibility import is_readable, readable_sql, story_sql


SA = "https://seekingalpha.com/news/4647846-volkswagen-and-gotion-high-tech-to-invest-322b"


def test_tracking_parameters_do_not_change_the_url_key():
    assert si.story_url_key(SA + "?feed_item_type=news") == si.story_url_key(SA)
    zacks = "https://www.zacks.com/stock/news/2997217/vw-taps-gotion"
    assert si.story_url_key(zacks + "?cid=CS-ZC-FT-analyst_blog") == si.story_url_key(zacks)


def test_identifying_query_parameters_are_kept():
    assert si.story_url_key("https://example.com/story?id=1") != \
        si.story_url_key("https://example.com/story?id=2")


def test_source_type():
    assert si.source_type("https://www.globenewswire.com/fr/news-release/x", "globenewswire.com") == "press_release"
    assert si.source_type("https://www.openpr.com/news/4646472/x", "openpr.com") == "press_release"
    assert si.source_type("https://menafn.com/1111730036/x", "menafn.com") == "press_release"
    assert si.source_type("https://example.com/x", "PR Newswire") == "press_release"
    assert si.source_type("https://asiatimes.com/2026/09/x/", "asiatimes.com") == "news"


def test_same_story_links_the_real_copies():
    assert si.same_story(
        "The Chinese company Gotion buys 49% of Volkswagen's battery plant in Sagunto",
        "The Chinese Gotion buys 49% of the Volkswagen battery plant in Sagunto")
    assert si.same_story(
        "Volkswagen-Gotion deal shows hard limits of China de-risking",
        "Volkswagen-Gotion Deal Shows Hard Limits Of China De-Risking")


def test_same_story_keeps_different_stories_apart():
    assert not si.same_story(
        "Volkswagen Taps Gotion to Expand Europe's LFP Battery Supply Chain",
        "Volkswagen Is Going Big On Cheaper LFP Batteries In Europe")


def test_window_bounds():
    assert si.window_bounds("2026-09-29T08:00:00+00:00") == ("2026-09-26", "2026-10-03")
    assert si.window_bounds("2026-09-29 08:00:00") == ("2026-09-26", "2026-10-03")
    assert si.window_bounds(None) is None
    assert si.window_bounds("not a date") is None


class FakeFacade:
    """Answers label_article's two queries from a list of stored rows."""

    def __init__(self, rows):
        self.rows = rows

    def _fetchone_with_rollback(self, stmt, params):
        for r in self.rows:
            if (r["topic"] == params["topic"] and r["url_key"] == params["key"]
                    and r["uri"] != params["uri"]):
                return (r["uri"],)
        return None

    def _fetchall_with_rollback(self, stmt, params):
        return [(r["uri"], r["title"], r.get("source_type")) for r in self.rows
                if r["topic"] == params["topic"] and r["duplicate_of"] is None
                and params["lo"] <= r["pub"] < params["hi"] and r["uri"] != params["uri"]]


TOPIC = "European Battery Industry"
ASIA = {"uri": "https://asiatimes.com/2026/09/volkswagen-gotion-deal/", "topic": TOPIC,
        "title": "Volkswagen-Gotion deal shows hard limits of China de-risking",
        "pub": "2026-09-29T06:00:00", "duplicate_of": None,
        "url_key": si.story_url_key("https://asiatimes.com/2026/09/volkswagen-gotion-deal/")}
SA_ROW = {"uri": SA, "topic": TOPIC, "title": "Volkswagen and Gotion to invest 3.22B",
          "pub": "2026-09-29T07:00:00", "duplicate_of": None, "url_key": si.story_url_key(SA)}


def test_tracking_copy_is_the_same_row():
    lab = si.label_article(FakeFacade([SA_ROW]), SA + "?feed_item_type=news",
                           "Volkswagen,Gotion to invest 3.22B", "seekingalpha.com",
                           TOPIC, "2026-09-29T07:05:00")
    assert lab["same_row"] == SA


def test_syndicated_copy_links_to_the_first_one():
    lab = si.label_article(FakeFacade([ASIA, SA_ROW]), "https://menafn.com/1111730036/x",
                           "Volkswagen-Gotion Deal Shows Hard Limits Of China De-Risking",
                           "menafn.com", TOPIC, "2026-09-30T10:00:00")
    assert lab["same_row"] is None
    assert lab["duplicate_of"] == ASIA["uri"]
    assert lab["source_type"] == "press_release"


def test_other_topic_or_far_date_does_not_link():
    other = dict(ASIA, topic="Other Topic")
    lab = si.label_article(FakeFacade([other]), "https://menafn.com/1/x", ASIA["title"],
                           "menafn.com", TOPIC, "2026-09-30T10:00:00")
    assert lab["duplicate_of"] is None
    lab = si.label_article(FakeFacade([ASIA]), "https://menafn.com/1/x", ASIA["title"],
                           "menafn.com", TOPIC, "2026-10-20T10:00:00")
    assert lab["duplicate_of"] is None


def test_readers_name_the_new_columns():
    assert "duplicate_of" in readable_sql("a") and "source_type" in readable_sql("a")
    assert "duplicate_of" in story_sql() and "topic_alignment_score" not in story_sql().split("NOT EXISTS")[0]


def test_is_readable_rows_in_hand():
    assert not is_readable({"duplicate_of": "https://x"})
    assert not is_readable({"source_type": "press_release", "topic": "European Battery Industry"})
    assert is_readable({"source_type": "news", "topic_alignment_score": 0.8})


def test_limits_found_by_the_50_link_check():
    # one-word titles on two different papers
    assert not si.same_story("Editorial", "Editorial")
    # different times are different summaries
    assert not si.same_story("AP Technology SummaryBrief at 6:33 p.m. EDT",
                             "AP Technology SummaryBrief at 6:07 p.m. EDT")
    # formulaic press-release titles link only when equal
    assert not si.same_story(
        "Radware Reports Second Quarter 2026 Financial Results",
        "PTC Therapeutics Provides Corporate Update and Reports Second Quarter 2026 Financial Results",
        press_release=True)
    assert si.same_story("Parsons Selected to Lead Design of $409M Roosevelt Bridge Replacement",
                         "Parsons Selected to Lead Design of $409M Roosevelt Bridge Replacement",
                         press_release=True)
    # a reworded wire story with the same numbers still links
    assert si.same_story("U.S. sanctions 10 people and firms from Iran and Venezuela over drone and missile trade",
                         "U.S. sanctions 10 people, firms from Iran and Venezuela over drone, missile trade")


def test_second_check_limits():
    # five significant tokens is too few for a near match
    assert not si.same_story("Israel strikes Hezbollah targets in Lebanon",
                             "Israel targets Hezbollah 'terrorist infrastructure' in south Lebanon strikes")
    # social posts never link on title
    row = {"uri": "https://bsky.app/profile/a/post/1", "topic": TOPIC,
           "title": "Switzerland rejects stricter interpretation of its neutrality",
           "pub": "2026-09-29T06:00:00", "duplicate_of": None, "url_key": "x"}
    lab = si.label_article(FakeFacade([row]), "https://bsky.app/profile/b/post/2",
                           "Switzerland rejects stricter interpretation of its neutrality",
                           "bluesky", TOPIC, "2026-09-29T08:00:00")
    assert lab["duplicate_of"] is None
