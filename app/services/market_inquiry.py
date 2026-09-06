"""Paid analyst calls booked from the market front page.

A reader picks 30 or 60 minutes, says what the call is about, and pays on
Stripe's hosted Checkout page. The success page then hands them the Google
Calendar booking link for the length they bought, and both they and the
editors get a mail saying the same. Stripe holds the card; we never see it.

The order of writes is what makes the flow safe against the two ways back
from Stripe arriving in either order (the buyer's browser on the success
page, and Stripe's webhook). The row exists before Checkout is asked for a
session, so both can find it. ``mark_paid`` flips ``created`` to ``paid``
with one guarded UPDATE, and each mail is claimed with a guarded UPDATE of
its own flag, so whichever arrives second does nothing.

The Stripe account is shared with saas.aunoo.ai, so this webhook also
receives that app's checkout events, and its webhook receives ours. A
session is ours only when its metadata says so and a row carries its id;
anything else is answered with 200 and ignored.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import Request
from sqlalchemy import text

from app.services.html_report_common import esc, html_document

logger = logging.getLogger(__name__)

META_APP = "aisocnews-inquiry"
INQUIRIES_PER_IP_PER_DAY = 10   # checkout attempts, its own counter, not the tip quota
SESSION_TTL_SECONDS = 30 * 60   # Stripe's minimum for a Checkout session

OPTIONS: Dict[int, Dict[str, Any]] = {
    30: {"label": "Analyst inquiry, 30 minutes", "cents": 25000,
         "env_price": "STRIPE_PRICE_INQUIRY_30",
         "env_booking": "MARKET_INQUIRY_BOOKING_URL_30",
         "blurb": "One vendor, one question. Enough to sanity-check a shortlist entry, "
                  "a claim in a press release, or a pricing conversation."},
    60: {"label": "Analyst inquiry, 60 minutes", "cents": 45000,
         "env_price": "STRIPE_PRICE_INQUIRY_60",
         "env_booking": "MARKET_INQUIRY_BOOKING_URL_60",
         "blurb": "The market, a shortlist, or a strategy question. Time to compare "
                  "vendors against each other and against where the market is going."},
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def price_id(minutes: int) -> Optional[str]:
    return os.getenv(OPTIONS[minutes]["env_price"]) or None


def booking_url(minutes: int) -> Optional[str]:
    return os.getenv(OPTIONS[minutes]["env_booking"]) or None


def is_configured() -> bool:
    """Everything the flow needs, or the button is not shown at all."""
    return bool(os.getenv("STRIPE_SECRET_KEY")) and all(
        price_id(m) and booking_url(m) for m in OPTIONS)


def _stripe():
    import stripe

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    return stripe


def fmt_amount(cents: int, currency: str = "usd") -> str:
    symbol = {"usd": "$", "eur": "€", "gbp": "£"}.get(currency.lower(), currency.upper() + " ")
    return f"{symbol}{cents / 100:,.0f}"


# ---------------------------------------------------------------------------
# Small helpers the routes need without importing market_monitor_routes
# ---------------------------------------------------------------------------

def conn():
    from app.database import get_database_instance

    return get_database_instance()._temp_get_connection()


def load_market(c, market_id: int, *, public_only: bool = True) -> Optional[Dict[str, Any]]:
    row = c.execute(text(
        "SELECT id, name, is_public FROM bw_markets WHERE id = :m"
    ), {"m": market_id}).mappings().first()
    if not row or (public_only and not row["is_public"]):
        return None
    return dict(row)


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for", "")
    return ((forwarded.split(",")[0].strip() if forwarded
             else (request.client.host if request.client else None)) or None)


def user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:400]


def base_url(request: Request) -> str:
    """Scheme and host as the reader sees them; nginx sets both headers."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def too_many_today(c, ip: Optional[str]) -> bool:
    if not ip:
        return False
    n = c.execute(text("""
        SELECT COUNT(*) FROM market_inquiries
         WHERE ip = :ip AND created_at > NOW() - INTERVAL '1 day'
    """), {"ip": ip}).scalar() or 0
    return int(n) >= INQUIRIES_PER_IP_PER_DAY


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def create_session(c, market: Dict[str, Any], *, minutes: int, subject: str,
                   name: str, email: str, ip: Optional[str], ua: str,
                   base: str) -> str:
    """Write the row, ask Stripe for a Checkout session, record its id, and
    return the URL to send the buyer to."""
    opt = OPTIONS[minutes]
    row_id = c.execute(text("""
        INSERT INTO market_inquiries (market_id, length_minutes, amount_cents, currency,
                                      subject, name, email, ip, user_agent)
        VALUES (:m, :len, :cents, 'usd', :subject, :name, :email, :ip, :ua)
        RETURNING id
    """), {"m": market["id"], "len": minutes, "cents": opt["cents"],
           "subject": subject or None, "name": name or None, "email": email,
           "ip": ip, "ua": ua}).scalar()
    c.commit()

    stripe = _stripe()
    prefix = f"{base}/api/market-monitor/markets/{int(market['id'])}/inquiry"
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": price_id(minutes), "quantity": 1}],
        customer_email=email,
        client_reference_id=str(row_id),
        metadata={"app": META_APP, "inquiry_id": str(row_id),
                  "market_id": str(market["id"]), "length_minutes": str(minutes),
                  "name": (name or "")[:200], "subject": (subject or "")[:490]},
        payment_intent_data={
            "description": f"{opt['label']} — {market['name']}",
            "metadata": {"app": META_APP, "inquiry_id": str(row_id)},
        },
        invoice_creation={"enabled": True},
        success_url=f"{prefix}/done?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{prefix}/cancelled",
        expires_at=int(time.time()) + SESSION_TTL_SECONDS,
    )
    c.execute(text("UPDATE market_inquiries SET stripe_session_id = :s WHERE id = :i"),
              {"s": session.id, "i": row_id})
    c.commit()
    logger.info("inquiry %s: checkout session %s (%d min) for market %s",
                row_id, session.id, minutes, market["id"])
    return session.url


def retrieve_session(session_id: str) -> Dict[str, Any]:
    """The session as plain dicts, whatever the SDK version wraps it in."""
    stripe = _stripe()
    session = stripe.checkout.Session.retrieve(session_id)
    return json.loads(str(session))


def event_from_webhook(payload: bytes, signature: str):
    stripe = _stripe()
    return stripe.Webhook.construct_event(
        payload, signature, os.getenv("STRIPE_WEBHOOK_SECRET") or "")


# ---------------------------------------------------------------------------
# After payment
# ---------------------------------------------------------------------------

def mark_paid(c, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Flip our row to ``paid`` once. Returns the row, or None when the
    session is not ours or is not paid yet."""
    meta = session.get("metadata") or {}
    if meta.get("app") != META_APP:
        return None
    if session.get("payment_status") != "paid":
        return None
    details = session.get("customer_details") or {}
    pi = session.get("payment_intent")
    if isinstance(pi, dict):
        pi = pi.get("id")
    row = c.execute(text("""
        UPDATE market_inquiries
           SET status = 'paid', paid_at = NOW(), stripe_payment_intent = :pi,
               email = COALESCE(:email, email), name = COALESCE(name, :name)
         WHERE stripe_session_id = :s AND status = 'created'
        RETURNING *
    """), {"pi": pi, "email": (details.get("email") or "").lower() or None,
           "name": details.get("name"), "s": session.get("id")}).mappings().first()
    if row is None:
        row = c.execute(text(
            "SELECT * FROM market_inquiries WHERE stripe_session_id = :s"
        ), {"s": session.get("id")}).mappings().first()
    c.commit()
    return dict(row) if row else None


def _claim(c, row_id: int, flag: str) -> bool:
    got = c.execute(text(
        f"UPDATE market_inquiries SET {flag} = true WHERE id = :i AND {flag} = false RETURNING id"
    ), {"i": row_id}).scalar()
    c.commit()
    return got is not None


def _release(c, row_id: int, flag: str) -> None:
    c.execute(text(f"UPDATE market_inquiries SET {flag} = false WHERE id = :i"), {"i": row_id})
    c.commit()


def _editors() -> List[str]:
    return [a.strip() for a in (os.getenv("MARKET_TRIAL_NOTIFY_EMAIL") or "").split(",")
            if a.strip()]


def notify(c, row: Dict[str, Any], market: Dict[str, Any]) -> None:
    """Mail the editors and the buyer, each at most once."""
    from app.services.email_service import EmailService

    svc = EmailService()
    if not svc.is_available():
        logger.warning("inquiry %s: mail is not configured; nothing sent", row["id"])
        return
    minutes = int(row["length_minutes"])
    amount = fmt_amount(int(row["amount_cents"]), row.get("currency") or "usd")
    link = booking_url(minutes) or ""
    editors = _editors()

    if editors and _claim(c, row["id"], "notified_editors"):
        lines = [f"Paid inquiry #{row['id']} — {market['name']}", "",
                 f"Length: {minutes} minutes ({amount})",
                 f"Name: {row.get('name') or '-'}", f"Email: {row['email']}",
                 f"About: {row.get('subject') or '-'}", "",
                 f"Stripe: https://dashboard.stripe.com/payments/{row.get('stripe_payment_intent') or ''}",
                 f"Booking link sent: {link}"]
        html_body = "<br>".join(esc(l) for l in lines)
        if not svc.send_email(editors, f"Paid inquiry ({minutes} min) — {market['name']}",
                              html_body, "\n".join(lines)):
            _release(c, row["id"], "notified_editors")

    if _claim(c, row["id"], "notified_buyer"):
        first = (row.get("name") or "").split(" ")[0] or "Hello"
        lines = [f"{first},", "",
                 f"Thank you. Your {minutes} minute analyst call on {market['name']} is paid ({amount}); "
                 "Stripe sends the receipt separately.", "",
                 "Pick a time here:", link, "",
                 "If none of the times suit, reply to this mail and we will find one.",
                 "", "Oliver Rochford", "Cyberfuturists"]
        html_body = "<br>".join(f'<a href="{esc(l)}">{esc(l)}</a>' if l == link else esc(l)
                                for l in lines)
        headers = {"Reply-To": editors[0]} if editors else None
        if not svc.send_email([row["email"]], "Your analyst call: pick a time",
                              html_body, "\n".join(lines), extra_headers=headers):
            _release(c, row["id"], "notified_buyer")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

INQUIRY_CSS = """
.mm-v2 .v2-inq form { display:grid; gap:14px; max-width:640px; }
.mm-v2 .v2-inq .opts { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px; }
.mm-v2 .v2-inq .opt { display:block; border:1px solid var(--n-line); border-radius:10px; padding:14px 16px; cursor:pointer; }
.mm-v2 .v2-inq .opt:has(input:checked) { border-color:var(--n-accent); box-shadow:0 0 0 1px var(--n-accent) inset; }
.mm-v2 .v2-inq .opt input { margin:0 8px 0 0; }
.mm-v2 .v2-inq .opt .price { float:right; font-weight:600; }
.mm-v2 .v2-inq .opt p { margin:8px 0 0; font-size:13px; color:var(--n-muted); }
.mm-v2 .v2-inq label.f { display:block; font-size:12px; letter-spacing:.05em; text-transform:uppercase; color:var(--n-muted); margin-bottom:4px; }
.mm-v2 .v2-inq input[type=text], .mm-v2 .v2-inq input[type=email], .mm-v2 .v2-inq textarea {
  width:100%; box-sizing:border-box; border:1px solid var(--n-line); border-radius:6px; padding:9px 10px; font:inherit; background:var(--n-panel); color:inherit; }
.mm-v2 .v2-inq textarea { min-height:110px; }
.mm-v2 .v2-inq .hp { position:absolute; left:-9999px; }
.mm-v2 .v2-inq .err { color:#ce2c31; font-size:14px; }
.mm-v2 .v2-inq .fine { font-size:13px; color:var(--n-muted); }
.mm-v2 .v2-inq .big { display:inline-block; font-size:16px; padding:12px 18px; }
"""


def _shell(market: Dict[str, Any], *, title: str, kicker: str, h1: str, sub: str,
           inner: str, front_href: str, about_href: str) -> str:
    from app.services.market_report_html import (
        _brand_line, _FONT_LINK, EXTRA_CSS, NEWS_CSS, DARK_CSS, V2_CSS)

    body = (f"{_FONT_LINK}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}{INQUIRY_CSS}</style>"
            '<div class="mm-news mm-v2"><div class="n-top">' + _brand_line()
            + '<nav class="n-pages" aria-label="Pages">'
            f'<a href="{esc(front_href)}">Front page</a><a href="{esc(about_href)}">About</a></nav>'
            f'<span class="n-market">{esc(market["name"])}</span></div>'
            '<main class="v2-grid"><div class="v2-main v2-one">'
            '<article class="v2-about v2-inq">'
            f'<header class="v2-mast"><div><p class="n-kicker">{esc(kicker)}</p>'
            f'<h1>{esc(h1)}</h1><p class="n-sub">{esc(sub)}</p></div></header>'
            + inner + "</article></div></main>"
            '<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])} · <a href="{esc(about_href)}">About</a> · '
            f'<a href="{esc(about_href)}#privacy">Privacy</a></span></div></div>')
    return html_document(title, body)


def build_inquiry_page(market: Dict[str, Any], *, front_href: str, about_href: str,
                       action: str, error: Optional[str] = None,
                       values: Optional[Dict[str, Any]] = None) -> str:
    v = values or {}
    chosen = int(v.get("minutes") or 30)
    opts = []
    for minutes, opt in OPTIONS.items():
        opts.append(
            f'<label class="opt"><input type="radio" name="minutes" value="{minutes}"'
            + (" checked" if minutes == chosen else "") + ">"
            f'<strong>{minutes} minutes</strong><span class="price">{fmt_amount(opt["cents"])}</span>'
            f'<p>{esc(opt["blurb"])}</p></label>')
    inner = (
        "<section><p>You are weighing a vendor, a shortlist, or a claim in a press release, "
        "and you want a second opinion from someone who has watched this market form. Book "
        "30 or 60 minutes with me. I did research at Gartner, named the SOAR category there, "
        "and now track every vendor in the AI SOC market for this site. Schedule an inquiry "
        "below.</p>"
        + (f'<p class="err" role="alert">{esc(error)}</p>' if error else "")
        + f'<form method="post" action="{esc(action)}">'
        f'<div class="opts">{"".join(opts)}</div>'
        '<div><label class="f" for="inq-subject">What is the call about?</label>'
        '<textarea id="inq-subject" name="subject" maxlength="2000" '
        'placeholder="The vendor, the question, or the decision you are weighing.">'
        f'{esc(v.get("subject") or "")}</textarea></div>'
        '<div><label class="f" for="inq-name">Your name</label>'
        f'<input id="inq-name" type="text" name="name" maxlength="200" autocomplete="name" required value="{esc(v.get("name") or "")}"></div>'
        '<div><label class="f" for="inq-email">Your email</label>'
        f'<input id="inq-email" type="email" name="email" maxlength="254" autocomplete="email" required value="{esc(v.get("email") or "")}"></div>'
        '<div class="hp" aria-hidden="true"><label>Website<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
        '<div><button type="submit" class="mm-btn big">Continue to payment</button></div>'
        '<p class="fine">Prices in US dollars. Payment is taken by Stripe; we never see your card. '
        "If none of the calendar times suit, reply to the confirmation mail and we will find one. "
        "A call can be rescheduled once without charge; refunds at our discretion before the call "
        "is booked.</p>"
        "</form></section>")
    return _shell(market, title=f"Schedule an inquiry — {market['name']}",
                  kicker="Schedule an inquiry", h1="Talk it through with the analyst",
                  sub="A paid 30 or 60 minute call on a vendor or the market.",
                  inner=inner, front_href=front_href, about_href=about_href)


def build_done_page(market: Dict[str, Any], row: Optional[Dict[str, Any]], *,
                    paid: bool, front_href: str, about_href: str) -> str:
    if row and paid:
        minutes = int(row["length_minutes"])
        link = booking_url(minutes) or ""
        inner = (f"<section><p>Thank you. Your {minutes} minute call is paid "
                 f"({fmt_amount(int(row['amount_cents']), row.get('currency') or 'usd')}). "
                 f"Stripe sends the receipt to {esc(row['email'])}, and a mail from us "
                 "repeats the link below.</p>"
                 f'<p><a class="mm-btn big" href="{esc(link)}">Pick a time for your call</a></p>'
                 '<p class="fine">If none of the times suit, reply to the confirmation mail '
                 "and we will find one.</p></section>")
        kicker, h1, sub = "Schedule an inquiry", "Paid. Now pick a time.", \
            "The calendar shows the slots that are open for your call."
    else:
        inner = ("<section><p>Stripe has your payment in hand but has not confirmed it yet. "
                 "This happens with some bank transfers and delayed methods. As soon as it "
                 "clears you will get a mail with the booking link.</p></section>")
        kicker, h1, sub = "Schedule an inquiry", "Payment pending", \
            "We will mail the booking link when Stripe confirms."
    return _shell(market, title=f"{h1} — {market['name']}", kicker=kicker, h1=h1,
                  sub=sub, inner=inner, front_href=front_href, about_href=about_href)


def build_cancelled_page(market: Dict[str, Any], *, retry_href: str, front_href: str,
                         about_href: str) -> str:
    inner = ("<section><p>Nothing was charged. If you changed your mind about the length "
             "or want to say more about the call first, the form is one step back.</p>"
             f'<p><a class="mm-btn big" href="{esc(retry_href)}">Back to the form</a></p></section>')
    return _shell(market, title=f"Not booked — {market['name']}",
                  kicker="Schedule an inquiry", h1="Not booked",
                  sub="You left Stripe’s page before paying.",
                  inner=inner, front_href=front_href, about_href=about_href)


def inquiry_href(market_id: int) -> str:
    return f"/api/market-monitor/markets/{int(market_id)}/inquiry"
