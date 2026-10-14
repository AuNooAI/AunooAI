"""Accounts run by software never get a role that puts them on a voices card.

On 14 Oct 2026 aisecwire listed reddit/ClaudeAI-mod-bot as a practitioner,
and bugfixing had skypilot-bot, cscr-bot and a dozen news-mirror bots as
analyst / press.
"""
import pytest

from app.services.social_profile_service import SocialProfileService, looks_automated


@pytest.mark.parametrize("handle,name,bio", [
    ("ClaudeAI-mod-bot", "Wilson", ""),
    ("AutoModerator", "", ""),
    ("skypilot-bot.bsky.social", "SkyPilot [Bot]", ""),
    ("seznamzpravy.zpravobot.news.ap.brid.gy", "Seznam Zprávy :bot:", ""),
    ("feedbot.unronritaro.net", "", ""),
    ("headline-feed.bsky.social", "News Ticker", "Automatically posts the top stories every hour"),
    ("mm-dday-bot.bsky.social", "DDay", "BOT che pubblica le news del sito, dal feed rss."),
])
def test_bots_are_recognised(handle, name, bio):
    assert looks_automated(handle, name, bio)


@pytest.mark.parametrize("handle,name,bio", [
    ("jtalbot", "James Talbot", "Security engineer"),
    ("abbot_ai", "The Abbot", ""),
    ("robotics_jane", "Jane", "I build robots"),
    ("chatbotguy", "Sam", "I write about chatbots and AI"),
    ("botanist_ann", "Ann", "botanist"),
    ("KirkDBorne", "Kirk Borne", "Data scientist"),
    ("techmeme.com", "Techmeme", "The essential tech news of the moment"),
])
def test_people_and_outlets_are_not(handle, name, bio):
    assert looks_automated(handle, name, bio) is None


def test_a_bot_read_as_a_person_moves_to_promoter_or_bot():
    meta = SocialProfileService._market_meta(
        {"role": "practitioner"}, "AI Security",
        {"handle": "ClaudeAI-mod-bot", "display_name": "Wilson", "bio": ""})
    assert meta["market_role"] == "promoter_or_bot"
    assert meta["automated"] == "name part 'bot'"


def test_a_vendor_reading_stands_and_people_are_untouched():
    vendor = SocialProfileService._market_meta(
        {"role": "vendor"}, "AI Security", {"handle": "bankrbot", "display_name": "", "bio": ""})
    assert vendor["market_role"] == "vendor" and "automated" not in vendor
    person = SocialProfileService._market_meta(
        {"role": "analyst_or_press"}, "AI Security",
        {"handle": "KirkDBorne", "display_name": "Kirk Borne", "bio": "Data scientist"})
    assert person["market_role"] == "analyst_or_press" and "automated" not in person
