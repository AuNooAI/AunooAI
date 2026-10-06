"""Retail deal listings never reach a brand feed. Fixtures are real rows that
Sunstar's Colgate and Oral-B topics approved in September 2026, and real
approved brand news that must keep flowing."""
import pytest

from app.services.deal_listing import deal_listing_reason

DEALS = [
    ("https://www.dealnews.com/Colgate-Optic-White-Advanced-Hydrogen-Peroxide", "Colgate Optic White Advanced Hydrogen Peroxide Toothpaste 3-Pack: $6.34 via Sub. & Save"),
    ("https://www.dansdeals.com/shopping-deals/amazon/3-pack-of-colgate-optic", "3 Pack Of Colgate Optic White Advanced Hydrogen Peroxide Toothpaste For $5.04-$6.34 Shipped"),
    ("https://slickdeals.net/f/20087952-sns-ac-18-42-3-6-pack-6-oz-colgate-c", "Select Accts: 6-pk 6-oz Colgate Cavity Protection Fluoride Toothpaste (Mint)"),
    ("https://www.dealigg.com/story-4-Pack-3-8-Oz-Colgate-Optic-White-Stain-", "Best Deal: 4-Pack 3.8-Oz Colgate Optic White Stain Fighter Clean Mint Paste Teeth Whitening"),
    ("https://www.ozbargain.com.au/node/976900", "[Prime] Oral-B Everyday Clean Electric Toothbrush Replacement Heads 16 Pack $41.90 ($37.71 S&S)"),
    ("https://moneysavingmom.com/free-oral-b-toothbrush-at-walmart", "FREE Oral-B Toothbrush at Walmart!"),
    ("https://example-news.com/shopping/colgate", "4-Pk 5.1-Oz Colgate Total Active Prevention Whitening Gel Toothpaste"),
    ("https://example-news.com/offers", "Colgate promo code: 20% off electric toothbrushes this Prime Day"),
]

NEWS = [
    ("https://uk.investing.com/news/stock-market-news/jp-morgan-flags", "J.P. Morgan flags negative catalyst at Haleon on weak sales momentum"),
    ("https://www.bbc.co.uk/news/articles/cm2dw27wywl2o", "Maidenhead toothpaste factory demolition plan gets go-ahead"),
    ("https://www.theguardian.com/society/2026/sep/22/the-rise-of-big-toothbrush", "The rise of Big Toothbrush: how did our mouths become such a lucrative market?"),
    ("https://www.gurufocus.com/news/9089733/cl-maintained-by-piper-sandler", "CL Maintained by Piper Sandler -- Price Target Lowered to $95"),
    ("https://equity-insider.com/colgate-palmolive-130-year-dividend", "Colgate-Palmolive's 130-Year Dividend Meets a Shrinking Home Market"),
    ("https://www.globenewswire.com/news-release/oral-care-market", "Oral Care Market to Reach $2.04 Billion by 2030, Says Report"),
    ("https://www.appbank.net/2026/09/24/iphone-news/3113610.php", "Sunstar releases the Ora2 WHITE CHECKER, an AI tool that visualises tooth whiteness"),
    ("https://www.reuters.com/business/nestle-offloads", "Nestle offloads brands for $1bn as it refocuses on coffee"),
    ("https://www.pharmatimes.com/news/wegovy-pill", "Wegovy pill goes on sale in the UK next month"),
    ("https://www.fiercebiotech.com/juniper-buys", "Juniper buys $2.73m in shares after results"),
]


@pytest.mark.parametrize("url,title", DEALS)
def test_deal_listings_are_recognised(url, title):
    assert deal_listing_reason(url, title) is not None


@pytest.mark.parametrize("url,title", NEWS)
def test_brand_news_and_earned_mentions_pass(url, title):
    assert deal_listing_reason(url, title) is None


def test_empty_input_is_not_a_deal():
    assert deal_listing_reason(None, None) is None
    assert deal_listing_reason("", "") is None
