"""Whose name a site's Market Monitor pages carry.

aisocnews.com is published by the Cyberfuturists, made using Aunoo, and the
pages were written for it: the byline, the kicker above the title, the About
page (which names Oliver Rochford Ltd as data controller) and the feed author.
A customer's market page is Aunoo's, not the Cyberfuturists', so on Oviva
those had been hand-edited out of the production tree, where the next copy
from canonical would have put them back (7 Oct 2026).

``MARKET_SITE_BRAND`` decides, per site:

- ``cyberfuturists`` (the default): the aisocnews pages, unchanged.
- ``aunoo``: an Aunoo byline, "Market monitor" above the title, no About page.
"""
from __future__ import annotations

import os

CYBERFUTURISTS = "cyberfuturists"
AUNOO = "aunoo"


def site_brand() -> str:
    value = (os.getenv("MARKET_SITE_BRAND") or CYBERFUTURISTS).strip().lower()
    return value if value in (CYBERFUTURISTS, AUNOO) else CYBERFUTURISTS


def is_cyberfuturists() -> bool:
    return site_brand() == CYBERFUTURISTS


def kicker() -> str:
    """The word above a page's title, before the period."""
    return "Cyberfuturists" if is_cyberfuturists() else "Market monitor"


def team() -> str:
    """Who writes the site's own analysis pieces."""
    return "the Cyberfuturists team" if is_cyberfuturists() else "our team"


def piece_author() -> str:
    """The byline of a published piece that names no author."""
    return "the Cyberfuturists" if is_cyberfuturists() else "Aunoo"


def feed_author() -> dict:
    """The JSON Feed ``authors`` entry."""
    if is_cyberfuturists():
        return {"name": "Cyberfuturists", "url": "https://cyberfuturists.com/"}
    return {"name": "Aunoo", "url": "https://aunoo.ai/"}


def about_page() -> bool:
    """Whether the site has the About page. Its text is the Cyberfuturists'
    legal and privacy statement, so an Aunoo-branded site has none."""
    return is_cyberfuturists()
