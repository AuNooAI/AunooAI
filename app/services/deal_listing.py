"""Retail deal listings are never news.

A brand monitor's keywords ("Colgate", "Oral-B", "Sensodyne") pull in price
listings from deal aggregators ("Best Deal: 4-Pack 3.8-Oz Colgate Optic White
..."), and the relevance judge approves them because they are about the brand's
products. On Sunstar they were about two thirds of the Colgate topic's approved
"press" in September 2026. This module recognises them from the host and the
title so the ingest step can reject them before any model call.

Measured on 90 days of Sunstar, Oviva and Panaya rows on 2026-10-05: every host
hit was a deal page; the title rule's only false positives were market-report
wires quoting "$17.83 Billion", which the money pattern now excludes.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# Deal aggregators and coupon sites. Hostnames only; subdomains match.
DEAL_HOSTS = {
    "dealigg.com", "slickdeals.net", "dansdeals.com", "ozbargain.com.au", "hotukdeals.com",
    "dealnews.com", "bensbargains.com", "mydealz.de", "preisjaeger.at", "dealabs.com",
    "pepper.com", "chollometro.com", "promodescuentos.com", "pelando.com.br",
    "camelcamelcamel.com", "woot.com", "brickseek.com", "couponfollow.com", "retailmenot.com",
    "offers.com", "dealmoon.com", "redflagdeals.com", "frugalfeeds.com.au", "latestdeals.co.uk",
    "coupons.com", "9to5toys.com", "clarkdeals.com", "hip2save.com", "thekrazycouponlady.com",
    "moneysavingmom.com",
}

# Title forms that only a price listing or a deals roundup uses. A plain price
# with cents ("$5.04") counts; a headline figure ("$2.04 Billion", "$2.73m") does not.
_TITLE_RE = re.compile(
    r"(best deal|deal alert|deals? (we|you|worth|to shop|live|just dropped|are back)|promo codes?|coupon"
    r"|\d+ ?% off|\$\d+\.\d\d(?![\d,])(?!\s*(?:b|m|t|bn|k|billion|million|trillion)\b)"
    r"|\b\d+[- ]?(?:pk|pack|count|ct)\b[^|]*\b(?:toothpaste|toothbrush|floss|mouthwash|for \$)"
    r"|prime day|black friday|cyber monday|clearance sale"
    r"|^free\b.{0,60}\bat (walmart|target|amazon|costco|cvs|walgreens|kroger|tesco|boots)\b)",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def deal_listing_reason(url: Optional[str], title: Optional[str]) -> Optional[str]:
    """Why this looks like a retail deal listing, or None when it does not."""
    host = _host(url or "")
    if host:
        for h in DEAL_HOSTS:
            if host == h or host.endswith("." + h):
                return f"deal site {h}"
    m = _TITLE_RE.search(title or "")
    if m:
        return f"title '{m.group(0).strip()}'"
    return None
