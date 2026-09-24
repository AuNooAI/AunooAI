"""Who wrote a social post, read by Jev instead of the social evaluation model.

The social evaluation step names the author's role (customer, dental
professional, press ...) in the same model call that scores relevance and
sentiment. On sunstar (24 Sep 2026) kimi and Jev disagreed on 31% of 1,420
posts; in a blind-labelled sample of 40 of those, kimi was right on 9 and Jev
on 32. Kimi called toothpaste users patients and fan accounts the brand; Jev's
one systematic miss was paid promotion, which it read as a customer talking.

So a site that switches this on keeps the model call for relevance and
sentiment, and takes the role from Jev, with one deterministic rule on top: a
post marked #ad, #sponsored, AD |, a TikTok Shop "yellow basket" and the like
is the brand's paid promotion when Jev read the author as a person (customer,
patient, caregiver or unknown). A shop's post stays a retailer.

Env:
    VOICES_ROLE_MODEL=jev   switch it on for this site (anything else: off)
    TYPESAFE_API_KEY        needed by typesafe_client; without it nothing changes
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

USE_CASE = "services.author_role_jev:read_role"
_MAX_WORKERS = 8

# One line per role in social_eval_service.AUTHOR_ROLES, saying the same thing
# as its role guide. Jev picks the role whose line fits the post best.
CRITERIA: Dict[str, str] = {
    "patient": "Uses, is on, is referred to or prescribed the brand's health, medical, care or treatment SERVICE (not a shop product)",
    "caregiver": "A relative or carer describing someone else's care",
    "clinician": "Doctor, GP, nurse, dietitian, pharmacist or therapist speaking as such (not dental)",
    "dental_professional": "Dentist, dental hygienist, orthodontist, dental clinic or dental student speaking as such",
    "customer": "Describes the brand's product in their own routine, purchase, haul, gift received or use, even without saying 'I use'",
    "academic": "Researcher, lecturer or scientist speaking as such",
    "professional": "Works in the brand's industry but not for the brand (analyst, consultant, commissioner, partner organisation)",
    "employee": "Works or worked for the brand, speaking as staff",
    "journalist": "A news outlet, reporter, newsletter, or a review or comparison site reporting on the brand",
    "investor": "Shareholder, stock commentator or market analyst",
    "brand": "The brand's own account (incl. regional or product accounts), its staff speaking for it, affiliates, or paid promotion (#ad, #PR, gifted, sponsored, affiliate links)",
    "retailer": "A shop, pharmacy, online seller or distributor offering the brand's products for sale",
    "competitor": "The author IS a rival company in the same market, its staff or its paid promotion. A third-party 'X vs Y' or review post is never this",
    "unknown": "Memes, jokes, figures of speech, fan reposts, commentary, or a recipe account naming the brand only as an ingredient or tag; nothing shows use of the product or another role",
}

# What the reader sees under "Why this role" in Voices.
REASONS: Dict[str, str] = {
    "patient": "Uses or is referred to the brand's health service",
    "caregiver": "Speaks about someone else's care",
    "clinician": "Speaks as a doctor, nurse or other health professional",
    "dental_professional": "Speaks as a dentist, hygienist or dental clinic",
    "customer": "Describes using or buying the product",
    "academic": "Speaks as a researcher",
    "professional": "Works in the industry, not for the brand",
    "employee": "Speaks as staff",
    "journalist": "Reports on the brand",
    "investor": "Comments on the business or the stock",
    "brand": "The brand's own account or its promotion",
    "retailer": "Sells the brand's products",
    "competitor": "A rival company's own account",
    "unknown": "Nothing in the post shows who is speaking",
}

# Marks a post as paid promotion. Tested on sunstar's 1,420 posts: "sponsored
# by" is left out because it matched news ("the dinner was sponsored by
# Haleon"), and a bare leading "Ad"/"Pr" counts only in capitals, because
# lower case starts ordinary sentences.
_PAID_PROMOTION = re.compile("|".join([
    r"#(?:ad|ads|advert|advertisement|pr|sponsored|sponsor|gifted|affiliate|publi|publicidad|anuncio"
    r"|werbung|anzeige|patrocinado|kerjasama|paidpartnership|paidpartner|partner|collab|createtowin"
    r"|shopeeaffiliate|amazinggracedeal)\b",
    r"^\s*(?:AD|PR|ANZEIGE|WERBUNG)\b",
    r"^\s*[\[\(](?:ad|pr|anzeige|werbung|publi)[\]\)]",
    r"\bpub[lI1]i\b",
    r"\bpaid partnership\b|\bgifted by\b|\baffiliate link\b|\bearns? (?:a )?commission\b|\breceive a commission\b",
    r"yellow basket|keranjang kuning|ตะกร้าเหลือง|#tiktokshop\w*|\btiktok ?shop\b|#shopee\w*|#lazada\w*",
    r"\buse (?:my )?code\b|\bdiscount code\b|\bpromo code\b",
]), re.IGNORECASE)
_LEADING_LABEL = re.compile(r"^\s*(?:ad|pr|anzeige|werbung)\b", re.IGNORECASE)
_LEADING_LABEL_CAPS = re.compile(r"^\s*(?:AD|PR|ANZEIGE|WERBUNG)\b")

# Readings the paid-promotion marker may overrule: a person talking. A shop
# with a discount code is still a retailer, and press is still press.
_PERSON_ROLES = {"customer", "patient", "caregiver", "unknown"}


def enabled() -> bool:
    return (os.getenv("VOICES_ROLE_MODEL") or "").strip().lower() == "jev"


def paid_promotion_marker(text: str) -> Optional[str]:
    """The marker that makes this post paid promotion, or None."""
    text = text or ""
    for m in _PAID_PROMOTION.finditer(text):
        if _LEADING_LABEL.match(m.group(0)) and not _LEADING_LABEL_CAPS.match(text):
            continue
        return m.group(0).strip()
    return None


def read_role(brand: str, context: str, competitors: List[str], post: Dict) -> Optional[Dict]:
    """{author_role, author_role_reason} for one post, or None when Jev did not answer."""
    from app.services import typesafe_client
    title = (post.get("title") or "")[:300]
    body = (post.get("summary") or post.get("content") or "")[:1500]
    state = {
        "brand": {"name": brand, "context": (context or "")[:600], "competitors": competitors},
        "post": {"platform": post.get("platform") or "", "author_handle": post.get("author") or "",
                 "title": title, "text": body},
    }
    questions = {"role": {
        "type": "choice",
        "instructions": ("Who is speaking in `post`, relative to `brand`? Judge from what the post says, "
                         "how the author speaks and the author handle. `brand.context` says what the brand "
                         "sells; `brand.competitors` are rival companies."),
        "criteria": CRITERIA,
    }}
    out = typesafe_client.system_one(state, questions, use_case=USE_CASE)
    if not out:
        return None
    answer = (out.get("answers") or {}).get("role") or {}
    probs = answer.get("probabilities") or {}
    role = max(probs, key=probs.get) if probs else answer.get("answer")
    if role not in CRITERIA:
        return None
    reason = REASONS[role]
    marker = paid_promotion_marker(f"{title}\n{body}")
    if marker and role in _PERSON_ROLES:
        role, reason = "brand", f"Paid promotion (marked {marker})"
    return {"author_role": role, "author_role_reason": reason}


def read_roles(brand: str, context: str, competitors: List[str],
               posts: List[Dict]) -> Dict[str, Dict]:
    """{uri: {author_role, author_role_reason}} for the posts Jev answered."""
    if not posts:
        return {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        results = list(pool.map(lambda p: read_role(brand, context, competitors, p), posts))
    out = {}
    for p, r in zip(posts, results):
        uri = p.get("uri") or p.get("url")
        if r and uri:
            out[uri] = r
    missed = len(posts) - len(out)
    if missed:
        logger.warning("author_role_jev: no answer for %d of %d posts (%s)", missed, len(posts), brand)
    return out


def rival_names(db, brand: str) -> List[str]:
    """Display names of the other enabled brands on the site."""
    from sqlalchemy import text
    try:
        rows = db.facade._execute_with_rollback(text(
            "SELECT display_name FROM bw_brands WHERE enabled = true AND display_name <> :b"),
            {"b": brand}).fetchall()
    except Exception as e:  # noqa: BLE001 - the role reads fine without the list
        logger.debug("author_role_jev: rival lookup failed: %s", e)
        return []
    return [r[0] for r in rows]
