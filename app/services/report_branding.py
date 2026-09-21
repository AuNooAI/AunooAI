"""Who the topic report is branded for, and who it is written about.

The deck, the Word document and the HTML export all used to hard-code
"WILEY HORIZONS" as the brand line and "Wiley" as the customer. On any
tenant that is not Wiley that is simply wrong copy: a Sunstar reader was
told on slide 7 that the analysis is calibrated to Wiley, and on slide 5
that it is framed for scientific publishing.

Two sources feed this module.

``REPORT_BRAND_EYEBROW`` carries the report's brand line. It already
exists and is already read by :mod:`app.services.horizons_html` and
:mod:`app.services.consensus_html`; this module reuses it rather than
inventing a second variable, and keeps ``WILEY HORIZONS`` as the default
so the Wiley tenants, which do not set it, render exactly as before.

The tenant's default organisational profile (the ``is_default`` row of
``organizational_profiles``) supplies the customer name and the sector.
That is the same profile the analysis prompts are already framed with, so
the slide claiming the analysis is calibrated to an organisation now names
the organisation it was actually calibrated to. ``REPORT_BRAND_ORG`` and
``REPORT_BRAND_SECTOR`` override it, which Wiley needs because its profile
is named "Wiley Scientific Publisher" and that does not read as a customer
name in a slide title.

Nothing here raises. A renderer that cannot reach the database still has
to produce a deck, so the fallbacks are wording that names nobody.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# The default is the neutral Aunoo brand, NOT a customer's. A tenant that
# has configured nothing must not ship a report headed with somebody else's
# name — pearson and sage are Wiley's competitors and run on this platform.
# The Wiley tenants opt in with REPORT_BRAND_EYEBROW=WILEY HORIZONS.
DEFAULT_EYEBROW = "AUNOO INTELLIGENCE"

# Wording used when we know neither the customer nor the sector.
_UNKNOWN_ORG = "your organisation"
_UNKNOWN_ORG_HEADING = "Your Organisation"
_UNKNOWN_SECTOR = "your sector"

# The organisational profiles every tenant is seeded with. They are sample
# rows, not a customer, and one of them is named after a real customer — a
# tenant that never set its own profile would otherwise address its report
# to Wiley. Treat a default that is still one of these as "unknown", so the
# copy names nobody instead of naming the wrong body.
_STOCK_PROFILE_NAMES = {
    "wiley scientific publisher",
    "generic enterprise",
    "cybersecurity organization",
    "financial institution",
    "insurance company",
    "manufacturing company",
    "concerned activist",
}


# Sectors for which the research-integrity framing on the team slide is
# the right one. Anywhere else, paper mills and citation rings are not
# the fraud the reader recognises.
_PUBLISHING_WORDS = ("publish", "journal", "academic", "scholar")


def brand_eyebrow() -> str:
    """The brand line, upper-case, as it appears on cover and section slides."""
    return (os.getenv("REPORT_BRAND_EYEBROW") or DEFAULT_EYEBROW).strip() or DEFAULT_EYEBROW


def brand_eyebrow_title() -> str:
    """The brand line in title case, for footers that read as prose."""
    return brand_eyebrow().title()


def brand_footer_credit() -> str:
    """The producer credit in a report footer.

    Normally "AunooAI <brand> Foresight". When the brand line is itself an
    Aunoo one — Sunstar sets REPORT_BRAND_EYEBROW to "AUNOO INTELLIGENCE" —
    the prefix is dropped, because "AunooAI Aunoo Intelligence Foresight"
    stutters.
    """
    brand = brand_eyebrow_title()
    if brand.lower().startswith("aunoo"):
        return f"{brand} Foresight"
    return f"AunooAI {brand} Foresight"


def _lower_for_sentence(text: str) -> str:
    """Lower-case Title-Case words so a sector reads inside a sentence.

    Acronyms and mixed-case names are left alone: "Academic Publishing"
    becomes "academic publishing", but "AI security tooling" keeps its AI.
    """
    out = []
    for word in text.split():
        if word[:1].isupper() and word[1:].islower():
            out.append(word.lower())
        else:
            out.append(word)
    return " ".join(out)


def _default_profile(db) -> dict:
    """The tenant's default organisational profile, or an empty dict."""
    if db is None:
        return {}
    try:
        from sqlalchemy import text as sa_text
        row = db.facade._execute_with_rollback(sa_text("""
            SELECT name, industry
            FROM organizational_profiles
            WHERE is_default IS TRUE
            ORDER BY id
            LIMIT 1
        """)).fetchone()
    except Exception as e:
        logger.warning("report branding: default org-profile lookup failed: %s", e)
        return {}
    if row is None:
        return {}
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def report_identity(db=None) -> dict:
    """Who this report is for, resolved once per rendered document.

    Returns ``org`` for use inside a sentence, ``org_heading`` for a slide
    title, ``sector`` already lower-cased for a sentence, and two flags
    saying whether either was actually resolved — a caller that gets
    ``org_known=False`` should choose wording that names nobody rather
    than print the fallback and hope.
    """
    profile = _default_profile(db)

    # A profile still sitting on its seeded name tells us nothing about who
    # this tenant is, so neither its name nor its industry may be printed.
    if (profile.get("name") or "").strip().lower() in _STOCK_PROFILE_NAMES:
        profile = {}

    org = (os.getenv("REPORT_BRAND_ORG") or "").strip() or (profile.get("name") or "").strip()
    sector = (os.getenv("REPORT_BRAND_SECTOR") or "").strip() or (profile.get("industry") or "").strip()

    org_known = bool(org)
    sector_known = bool(sector)

    return {
        "org": org if org_known else _UNKNOWN_ORG,
        "org_heading": org if org_known else _UNKNOWN_ORG_HEADING,
        "org_known": org_known,
        "sector": _lower_for_sentence(sector) if sector_known else _UNKNOWN_SECTOR,
        "sector_known": sector_known,
        "sector_is_publishing": sector_known and any(
            w in sector.lower() for w in _PUBLISHING_WORDS
        ),
    }


def unknown_identity() -> dict:
    """The name-free identity, for renderers with no database to consult."""
    return report_identity(db=None)
