"""The intelligence feed: monthly subscriptions sold from the front page.

Two plans. **Intelligence feed** ($179/month) turns the shared view into
the whole market: every vendor named, the KPIs and metrics that the
public tier withholds, on every page of the site. **Intelligence feed +
MCP access** ($279/month) adds a bearer key for the app's MCP server, so
the buyer's AI tools can query the same data programmatically.

The buyer pays on Stripe's hosted Checkout page in subscription mode.
What they receive is an access link — the site URL with a ``key=``
parameter that the report route resolves to the full entitlement — and,
on the MCP plan, an ``aunoo_`` bearer key. Both are minted exactly once:
the row exists before Checkout is asked for a session, ``activate`` flips
``created`` to ``active`` with one guarded UPDATE, and only that winner
mints credentials and sends mail, so the webhook and the buyer's browser
can arrive in either order without double-minting.

Stripe owns the lifecycle. ``customer.subscription.updated`` moves the
row between ``active`` and ``past_due`` (access is kept through Stripe's
retry window), and ``customer.subscription.deleted`` cancels it: the site
key stops resolving on the next request and the MCP key is revoked.

MCP keys must belong to an active user (``mcp_api_keys.username`` is a
foreign key), so subscriber keys hang off one dedicated service user,
``mcp-subscriber``, created on first use with an unknowable password.
Deactivating that user is the kill switch for every subscriber key at
once, and per-key audit stays intact through ``mcp_tool_calls``.

The Stripe account is shared with saas.aunoo.ai and the analyst-call
flow; a session or subscription is ours only when its metadata says so.
"""

import json
import logging
import os
import secrets
import time
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import text

from app.services.html_report_common import esc
from app.services.market_inquiry import (  # shared plumbing, same Stripe account
    EMAIL_RE,  # noqa: F401 — re-exported for the routes
    _shell,
    _stripe,
    base_url,  # noqa: F401
    client_ip,  # noqa: F401
    conn,  # noqa: F401
    fmt_amount,
    load_market,  # noqa: F401
    user_agent,  # noqa: F401
)

logger = logging.getLogger(__name__)

META_APP = "aisocnews-subscription"
CHECKOUTS_PER_IP_PER_DAY = 10
SESSION_TTL_SECONDS = 30 * 60

MCP_SERVICE_USERNAME = "mcp-subscriber"
MCP_SERVICE_EMAIL = "mcp-subscriber@aisocnews.com"

PLANS: Dict[str, Dict[str, Any]] = {
    "dataset": {
        "label": "Intelligence feed", "cents": 17900,
        "env_price": "STRIPE_PRICE_SUB_DATASET",
        "blurb": "The whole site with nothing held back. You see every vendor "
                 "we monitor and the numbers behind the rankings: who is "
                 "getting attention, who is hiring, and how they compare."},
    "mcp": {
        "label": "Intelligence feed + MCP access", "cents": 27900,
        "env_price": "STRIPE_PRICE_SUB_MCP",
        "blurb": "Everything in the intelligence feed, plus a key for our MCP "
                 "server. Claude, ChatGPT or your own agents can then query "
                 "the data directly instead of reading the pages."},
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def price_id(plan: str) -> Optional[str]:
    return os.getenv(PLANS[plan]["env_price"]) or None


def is_configured() -> bool:
    """Everything the flow needs, or the buttons are not shown at all.

    The webhook secret is part of it on purpose: without the lifecycle
    events a cancelled subscription would keep its access forever, so the
    product only sells once cancellations actually revoke.
    """
    return (bool(os.getenv("STRIPE_SECRET_KEY"))
            and bool(os.getenv("STRIPE_SUB_WEBHOOK_SECRET"))
            and all(price_id(p) for p in PLANS))


def subscribe_href(market_id: int) -> str:
    return f"/api/market-monitor/markets/{int(market_id)}/subscribe"


def too_many_today(c, ip: Optional[str]) -> bool:
    if not ip:
        return False
    n = c.execute(text("""
        SELECT COUNT(*) FROM market_subscriptions
         WHERE ip = :ip AND created_at > NOW() - INTERVAL '1 day'
    """), {"ip": ip}).scalar() or 0
    return int(n) >= CHECKOUTS_PER_IP_PER_DAY


# ---------------------------------------------------------------------------
# The access credential
# ---------------------------------------------------------------------------

def hash_key(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _new_access_token() -> str:
    return "dsk_" + secrets.token_urlsafe(24)


def active_by_key(c, market_id: int, token: str) -> Optional[Dict[str, Any]]:
    """The subscription this key belongs to, when it is good for this
    market. ``past_due`` still resolves: access is kept through Stripe's
    retry window and cut only when the subscription is actually gone."""
    if not token or len(token) > 120:
        return None
    row = c.execute(text("""
        SELECT * FROM market_subscriptions
         WHERE access_token_hash = :h AND market_id = :m
           AND status IN ('active', 'past_due')
    """), {"h": hash_key(token), "m": int(market_id)}).mappings().first()
    return dict(row) if row else None


def help_href(site: Optional[str], market_id: int) -> str:
    """The MCP setup guide, on whichever host the buyer bought on. The
    public site has the short /mcp-help redirect; the mail uses the full
    path so it works regardless."""
    base = (site or os.getenv("APP_URL") or "").rstrip("/")
    return f"{base}/api/market-monitor/markets/{int(market_id)}/subscribe/help"


def access_href(site: Optional[str], market_id: int, token: str) -> str:
    """The link the buyer opens. On the public host the front page is
    ``/``; anywhere else it is the report route."""
    app_host = (urlparse(os.getenv("APP_URL") or "").hostname or "").lower()
    host = (urlparse(site or "").hostname or "").lower()
    if host and host != app_host:
        return f"{(site or '').rstrip('/')}/?key={token}"
    base = (site or os.getenv("APP_URL") or "").rstrip("/")
    return f"{base}/api/market-monitor/markets/{int(market_id)}/report.html?view=v2&key={token}"


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def create_session(c, market: Dict[str, Any], *, plan: str, name: str,
                   email: str, ip: Optional[str], ua: str, base: str) -> str:
    """Write the row, ask Stripe for a subscription Checkout session,
    record its id, and return the URL to send the buyer to."""
    opt = PLANS[plan]
    row_id = c.execute(text("""
        INSERT INTO market_subscriptions (market_id, plan, amount_cents, currency,
                                          name, email, site, ip, user_agent)
        VALUES (:m, :plan, :cents, 'usd', :name, :email, :site, :ip, :ua)
        RETURNING id
    """), {"m": market["id"], "plan": plan, "cents": opt["cents"],
           "name": name or None, "email": email, "site": base[:200],
           "ip": ip, "ua": ua}).scalar()
    c.commit()

    stripe = _stripe()
    prefix = f"{base}/api/market-monitor/markets/{int(market['id'])}/subscribe"
    meta = {"app": META_APP, "subscription_row": str(row_id),
            "market_id": str(market["id"]), "plan": plan}
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id(plan), "quantity": 1}],
        customer_email=email,
        client_reference_id=str(row_id),
        metadata=meta,
        # The Subscription object carries the same metadata, so the
        # lifecycle events (updated, deleted) can be recognised as ours.
        subscription_data={
            "description": f"{opt['label']} — {market['name']}",
            "metadata": meta,
        },
        # Promotion codes are how a discounted or free subscription is
        # sold (and how the flow is tested end to end without money);
        # if_required skips card collection only when nothing will ever
        # be due, i.e. a 100%-off-forever code.
        allow_promotion_codes=True,
        payment_method_collection="if_required",
        success_url=f"{prefix}/done?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{prefix}/cancelled",
        expires_at=int(time.time()) + SESSION_TTL_SECONDS,
    )
    c.execute(text("UPDATE market_subscriptions SET stripe_session_id = :s WHERE id = :i"),
              {"s": session.id, "i": row_id})
    c.commit()
    logger.info("subscription %s: checkout session %s (%s) for market %s",
                row_id, session.id, plan, market["id"])
    return session.url


def retrieve_session(session_id: str) -> Dict[str, Any]:
    stripe = _stripe()
    session = stripe.checkout.Session.retrieve(session_id)
    return json.loads(str(session))


def event_from_webhook(payload: bytes, signature: str):
    stripe = _stripe()
    return stripe.Webhook.construct_event(
        payload, signature, os.getenv("STRIPE_SUB_WEBHOOK_SECRET") or "")


# ---------------------------------------------------------------------------
# Fulfilment
# ---------------------------------------------------------------------------

def _ensure_mcp_user() -> None:
    """The service user every subscriber key belongs to. The password is
    random and thrown away, so the account cannot be logged into — it
    exists only to satisfy the key table's foreign key and to be the one
    switch that cuts every subscriber key at once."""
    from app.database import get_database_instance
    from app.security.auth import get_password_hash

    facade = get_database_instance().facade
    if facade.get_user_by_username(MCP_SERVICE_USERNAME):
        return
    facade.create_user(MCP_SERVICE_USERNAME, MCP_SERVICE_EMAIL,
                       get_password_hash(secrets.token_urlsafe(48)),
                       role="user", is_active=True)
    logger.info("subscription: created MCP service user %s", MCP_SERVICE_USERNAME)


def _mint_mcp_key(row_id: int, email: str) -> Tuple[str, int]:
    from app.mcp_access import keys as mcp_keys

    _ensure_mcp_user()
    plaintext, key_row = mcp_keys.mint_key(
        username=MCP_SERVICE_USERNAME,
        name=f"subscription {row_id} ({email})",
        created_by=MCP_SERVICE_USERNAME)
    return plaintext, int(key_row["id"])


def activate(c, session: Dict[str, Any]
             ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Flip our row to ``active`` once and mint its credentials.

    Returns ``(row, access_token, mcp_key)``. The tokens are only present
    for the caller that won the guarded UPDATE — the plaintexts exist
    nowhere else, so that caller is the one that mails them out. The
    loser gets the row and two Nones and sends nothing.
    """
    meta = session.get("metadata") or {}
    if meta.get("app") != META_APP:
        return None, None, None
    if session.get("payment_status") != "paid":
        return None, None, None
    details = session.get("customer_details") or {}
    sub_id = session.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    row = c.execute(text("""
        UPDATE market_subscriptions
           SET status = 'active', activated_at = NOW(),
               stripe_customer_id = :cust, stripe_subscription_id = :sub,
               email = COALESCE(:email, email), name = COALESCE(name, :name)
         WHERE stripe_session_id = :s AND status = 'created'
        RETURNING *
    """), {"cust": session.get("customer"), "sub": sub_id,
           "email": (details.get("email") or "").lower() or None,
           "name": details.get("name"), "s": session.get("id")}).mappings().first()
    if row is None:
        row = c.execute(text(
            "SELECT * FROM market_subscriptions WHERE stripe_session_id = :s"
        ), {"s": session.get("id")}).mappings().first()
        c.commit()
        return (dict(row) if row else None), None, None
    row = dict(row)
    c.commit()

    access_token = _new_access_token()
    c.execute(text("""
        UPDATE market_subscriptions
           SET access_token_hash = :h, access_token_prefix = :p WHERE id = :i
    """), {"h": hash_key(access_token), "p": access_token[:12], "i": row["id"]})
    c.commit()

    mcp_key = None
    if row["plan"] == "mcp":
        try:
            mcp_key, key_id = _mint_mcp_key(int(row["id"]), row["email"])
            c.execute(text("UPDATE market_subscriptions SET mcp_key_id = :k WHERE id = :i"),
                      {"k": key_id, "i": row["id"]})
            c.commit()
        except Exception:  # noqa: BLE001 — the dataset half still works
            logger.exception("subscription %s: MCP key minting failed; "
                             "mint one by hand for %s", row["id"], row["email"])
    logger.info("subscription %s activated (%s, %s)",
                row["id"], row["plan"], row.get("stripe_subscription_id"))
    return row, access_token, mcp_key


def reissue(c, session: Dict[str, Any]
            ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Rotate a live subscription's credentials and return the new
    plaintexts.

    The recovery path for a lost link or a mail that never arrived. The
    caller proves themselves with the Checkout ``session_id`` — the
    secret in Stripe's success redirect, which only the buyer holds.
    Rotation, not retrieval: the old link stops resolving and the old
    MCP key is revoked, so a leaked credential is also fixed by this.
    ``notified_buyer`` is reset first, so ``notify`` mails the fresh
    credentials again.
    """
    meta = session.get("metadata") or {}
    if meta.get("app") != META_APP:
        return None, None, None
    row = c.execute(text(
        "SELECT * FROM market_subscriptions WHERE stripe_session_id = :s"
    ), {"s": session.get("id")}).mappings().first()
    if row is None or row["status"] not in ("active", "past_due"):
        return (dict(row) if row else None), None, None
    row = dict(row)

    access_token = _new_access_token()
    c.execute(text("""
        UPDATE market_subscriptions
           SET access_token_hash = :h, access_token_prefix = :p,
               notified_buyer = false
         WHERE id = :i
    """), {"h": hash_key(access_token), "p": access_token[:12], "i": row["id"]})
    c.commit()

    mcp_key = None
    if row["plan"] == "mcp":
        old_key_id = row.get("mcp_key_id")
        try:
            mcp_key, key_id = _mint_mcp_key(int(row["id"]), row["email"])
            c.execute(text("UPDATE market_subscriptions SET mcp_key_id = :k WHERE id = :i"),
                      {"k": key_id, "i": row["id"]})
            c.commit()
            if old_key_id:
                from app.mcp_access import store as mcp_store
                mcp_store.revoke_api_key(int(old_key_id))
        except Exception:  # noqa: BLE001 — the dataset half still rotates
            logger.exception("subscription %s: MCP key rotation failed; "
                             "mint one by hand for %s", row["id"], row["email"])
    logger.info("subscription %s credentials re-issued", row["id"])
    return row, access_token, mcp_key


def _find_by_subscription(c, stripe_subscription_id: Optional[str],
                          meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if meta.get("app") != META_APP or not stripe_subscription_id:
        return None
    row = c.execute(text(
        "SELECT * FROM market_subscriptions WHERE stripe_subscription_id = :s"
    ), {"s": stripe_subscription_id}).mappings().first()
    return dict(row) if row else None


def apply_lifecycle(c, subscription: Dict[str, Any], *, deleted: bool) -> Optional[str]:
    """Keep our row in step with Stripe's Subscription object. Returns the
    status we moved to, or None when the event is not ours or changes
    nothing."""
    row = _find_by_subscription(c, subscription.get("id"),
                                subscription.get("metadata") or {})
    if row is None:
        return None
    stripe_status = subscription.get("status") or ""
    if deleted or stripe_status in ("canceled", "incomplete_expired"):
        target = "cancelled"
    elif stripe_status in ("past_due", "unpaid"):
        target = "past_due"
    elif stripe_status in ("active", "trialing"):
        target = "active"
    else:
        return None
    if target == row["status"]:
        return None
    if target == "cancelled":
        got = c.execute(text("""
            UPDATE market_subscriptions SET status = 'cancelled', cancelled_at = NOW()
             WHERE id = :i AND status <> 'cancelled' RETURNING mcp_key_id
        """), {"i": row["id"]}).mappings().first()
        c.commit()
        if got and got["mcp_key_id"]:
            from app.mcp_access import store as mcp_store
            mcp_store.revoke_api_key(int(got["mcp_key_id"]))
        logger.info("subscription %s cancelled (stripe %s)", row["id"], subscription.get("id"))
        return "cancelled"
    # active <-> past_due: visibility only; nothing is revoked in the
    # retry window, so nothing needs re-minting on recovery.
    c.execute(text("UPDATE market_subscriptions SET status = :t WHERE id = :i AND status <> 'cancelled'"),
              {"t": target, "i": row["id"]})
    c.commit()
    logger.info("subscription %s -> %s (stripe %s)", row["id"], target, subscription.get("id"))
    return target


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------

def _claim(c, row_id: int, flag: str) -> bool:
    got = c.execute(text(
        f"UPDATE market_subscriptions SET {flag} = true WHERE id = :i AND {flag} = false RETURNING id"
    ), {"i": row_id}).scalar()
    c.commit()
    return got is not None


def _release(c, row_id: int, flag: str) -> None:
    c.execute(text(f"UPDATE market_subscriptions SET {flag} = false WHERE id = :i"), {"i": row_id})
    c.commit()


def _editors():
    return [a.strip() for a in (os.getenv("MARKET_TRIAL_NOTIFY_EMAIL") or "").split(",")
            if a.strip()]


def notify(c, row: Dict[str, Any], market: Dict[str, Any], *,
           access_token: str, mcp_key: Optional[str]) -> None:
    """Mail the editors and the buyer, each at most once. Only the caller
    holding the plaintexts can send these, which is exactly the caller
    that won ``activate``."""
    from app.services.email_service import EmailService

    svc = EmailService()
    if not svc.is_available():
        logger.error("subscription %s: mail is not configured; the buyer has "
                     "no way to receive the access link", row["id"])
        return
    plan = PLANS[row["plan"]]
    amount = fmt_amount(int(row["amount_cents"]), row.get("currency") or "usd")
    link = access_href(row.get("site"), int(row["market_id"]), access_token)
    editors = _editors()

    if editors and _claim(c, row["id"], "notified_editors"):
        lines = [f"New subscription #{row['id']} — {market['name']}", "",
                 f"Plan: {plan['label']} ({amount}/month)",
                 f"Name: {row.get('name') or '-'}", f"Email: {row['email']}",
                 f"Stripe subscription: {row.get('stripe_subscription_id') or '-'}",
                 f"MCP key minted: {'yes' if mcp_key else 'no'}"]
        html_body = "<br>".join(esc(l) for l in lines)
        if not svc.send_email(editors, f"New subscription ({plan['label']}) — {market['name']}",
                              html_body, "\n".join(lines)):
            _release(c, row["id"], "notified_editors")

    if _claim(c, row["id"], "notified_buyer"):
        first = (row.get("name") or "").split(" ")[0] or "Hello"
        mcp_url = (os.getenv("APP_URL") or "").rstrip("/") + "/mcp"
        lines = [f"{first},", "",
                 f"Thank you. Your {market['name']} intelligence feed is active "
                 f"({amount}/month); Stripe sends the receipt separately.", "",
                 "This link opens the whole site, with every vendor and every figure. "
                 "Bookmark it and treat it like a password:", link]
        guide = help_href(row.get("site"), int(row["market_id"]))
        if mcp_key:
            lines += ["",
                      "Your MCP key, for Claude, ChatGPT or your own agents:", mcp_key, "",
                      f"Point your MCP client at {mcp_url} and send the key as "
                      "a bearer token (Authorization: Bearer <key>). This mail is "
                      "the only place the key appears; we store only a hash.", "",
                      "Setup instructions for each client, with copy-paste configs:", guide]
        lines += ["",
                  "If you cancel, access ends with the paid period. Questions or a "
                  "lost link: reply to this mail.",
                  "", "Oliver Rochford", "Cyberfuturists"]
        html_body = "<br>".join(f'<a href="{esc(l)}">{esc(l)}</a>' if l in (link, guide)
                                else esc(l) for l in lines)
        headers = {"Reply-To": editors[0]} if editors else None
        if not svc.send_email([row["email"]], f"Your {market['name']} intelligence feed",
                              html_body, "\n".join(lines), extra_headers=headers):
            _release(c, row["id"], "notified_buyer")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def roster_counts(c, market_id: int) -> Dict[str, int]:
    """How many vendors the market tracks and how many the free view
    names — fetched live so the plans page never quotes a stale number."""
    from app.services import market_entitlements as ent

    total = c.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded'
    """), {"m": int(market_id)}).scalar() or 0
    return {"total": int(total), "named": min(ent.public_vendor_limit(), int(total))}


def _whats_inside(totals: Optional[Dict[str, int]]) -> str:
    """The concrete difference between the free view and the feed. Every
    line here must stay true to what the entitlement code actually
    withholds; when the policy moves, this list moves with it."""
    if not totals:
        return ""
    total, named = totals["total"], totals["named"]
    return (
        "<h2>What the free view holds back</h2>"
        f"<p>We monitor {total} vendors in this market. The free view reports on all of "
        f"them by name, but its rankings and figures stop at the {named} most-covered "
        "companies. The feed removes that cap everywhere:</p>"
        "<ul>"
        f"<li>The attention chart shows engagement and earned-coverage figures, with "
        f"movement against the period before, for all {total} vendors instead of {named}.</li>"
        "<li>The hiring section names who is hiring. The free view keeps the counts "
        "but withholds which vendor each one belongs to.</li>"
        "<li>The analyst view — the benchmark that scores and compares every vendor's "
        "activity, coverage and momentum — is masked on the free site and open in "
        "the feed.</li>"
        "<li>Every section page, period and chart works the same way: no withheld "
        "rows, no masked names.</li>"
        "</ul>"
        f"<p>You also get industry benchmarking data for all {total} vendors, their "
        "latest announcements as we collect them (launches, funding, partnerships, "
        "customer wins), and marketing reach data: each vendor's audience, posting "
        "activity, engagement and earned coverage.</p>"
        "<p>The MCP plan adds the layer under the pages: the collected articles and "
        "posts, vendor profiles and sentiment, queryable by your own tools rather "
        "than read off a chart.</p>")


def build_subscribe_page(market: Dict[str, Any], *, front_href: str, about_href: str,
                         action: str, error: Optional[str] = None,
                         values: Optional[Dict[str, Any]] = None,
                         totals: Optional[Dict[str, int]] = None) -> str:
    v = values or {}
    chosen = v.get("plan") or "dataset"
    opts = []
    for plan, opt in PLANS.items():
        opts.append(
            f'<label class="opt"><input type="radio" name="plan" value="{plan}"'
            + (" checked" if plan == chosen else "") + ">"
            f'<strong>{esc(opt["label"])}</strong>'
            f'<span class="price">{fmt_amount(opt["cents"])}/mo</span>'
            f'<p>{esc(opt["blurb"])}</p></label>')
    inner = (
        "<section><p>The free view shows every vendor's news and posts, but it names only "
        "the most-covered companies in the rankings and keeps the figures for paying "
        "readers. The intelligence feed opens the rest of the site: the full vendor list, "
        "the numbers behind the charts, and the analyst view. If you would rather have the "
        "same data in your AI tools than on a page, the MCP plan adds a key for that.</p>"
        + _whats_inside(totals)
        + (f'<p class="err" role="alert">{esc(error)}</p>' if error else "")
        + f'<form method="post" action="{esc(action)}">'
        f'<div class="opts">{"".join(opts)}</div>'
        '<div><label class="f" for="sub-name">Your name</label>'
        f'<input id="sub-name" type="text" name="name" maxlength="200" autocomplete="name" required value="{esc(v.get("name") or "")}"></div>'
        '<div><label class="f" for="sub-email">Your email</label>'
        f'<input id="sub-email" type="email" name="email" maxlength="254" autocomplete="email" required value="{esc(v.get("email") or "")}"></div>'
        '<div class="hp" aria-hidden="true"><label>Website<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
        '<div><button type="submit" class="mm-btn big">Continue to payment</button></div>'
        '<p class="fine">Prices in US dollars, billed monthly by Stripe; we never see your card. '
        "Cancel any time from the Stripe receipt; access runs to the end of the paid month. "
        "The access link and key are for you and your team, not for republication.</p>"
        "</form></section>")
    return _shell(market, title=f"Intelligence feed — {market['name']}",
                  kicker="Intelligence feed", h1="Read the whole market",
                  sub="A monthly subscription that opens the whole site, with "
                      "optional MCP access for your AI tools.",
                  inner=inner, front_href=front_href, about_href=about_href)


def build_done_page(market: Dict[str, Any], row: Optional[Dict[str, Any]], *,
                    paid: bool, access_token: Optional[str], mcp_key: Optional[str],
                    front_href: str, about_href: str,
                    reissue_action: Optional[str] = None,
                    session_id: Optional[str] = None) -> str:
    if row and paid and access_token:
        link = access_href(row.get("site"), int(row["market_id"]), access_token)
        mcp_url = (os.getenv("APP_URL") or "").rstrip("/") + "/mcp"
        inner = (f"<section><p>Thank you. Your {esc(PLANS[row['plan']]['label'])} subscription "
                 f"is active ({fmt_amount(int(row['amount_cents']))}/month). A mail to "
                 f"{esc(row['email'])} repeats everything below.</p>"
                 f'<p><a class="mm-btn big" href="{esc(link)}">Open the full dataset</a></p>'
                 '<p class="fine">Bookmark that link and treat it like a password.</p>'
                 + (("<p>Your MCP key, shown only here and in the mail:</p>"
                     f"<p><code>{esc(mcp_key)}</code></p>"
                     f'<p class="fine">Point your MCP client at {esc(mcp_url)} and send the '
                     'key as a bearer token. The <a href="'
                     + esc(f"{subscribe_href(int(row['market_id']))}/help")
                     + '">setup guide</a> has copy-paste configs for Claude, Cursor '
                     "and VS Code.</p>") if mcp_key else "")
                 + "</section>")
        kicker, h1, sub = "Intelligence feed", "Your access is ready", \
            "The link below opens the whole site from now on."
    elif row and paid:
        inner = ("<section><p>Your subscription is active, and your access link went to "
                 f"{esc(row['email'])} the moment payment cleared.</p>"
                 + ((f'<form method="post" action="{esc(reissue_action)}">'
                     f'<input type="hidden" name="session_id" value="{esc(session_id or "")}">'
                     '<button type="submit" class="mm-btn big">The mail is not there — re-issue my access</button></form>'
                     '<p class="fine">This makes a fresh link (and key on the MCP plan), shows it '
                     "here, sends the mail again, and invalidates the old one.</p>")
                    if reissue_action else "")
                 + "</section>")
        kicker, h1, sub = "Intelligence feed", "Your access link is in your mail", \
            "It went out the moment payment cleared."
    elif row and row.get("status") == "cancelled":
        inner = ("<section><p>This subscription has been cancelled, so there is nothing to "
                 "re-issue. If that is a surprise, reply to your confirmation mail.</p></section>")
        kicker, h1, sub = "Intelligence feed", "No longer active", \
            "Access ended with the subscription."
    else:
        inner = ("<section><p>Stripe has your payment in hand but has not confirmed it yet. "
                 "As soon as it clears you will get a mail with your access link.</p></section>")
        kicker, h1, sub = "Intelligence feed", "Payment pending", \
            "We will mail your access link when Stripe confirms."
    return _shell(market, title=f"{h1} — {market['name']}", kicker=kicker, h1=h1,
                  sub=sub, inner=inner, front_href=front_href, about_href=about_href)


def build_cancelled_page(market: Dict[str, Any], *, retry_href: str, front_href: str,
                         about_href: str) -> str:
    inner = ("<section><p>Nothing was charged and nothing recurs. If you want to look at the "
             "plans again, the form is one step back.</p>"
             f'<p><a class="mm-btn big" href="{esc(retry_href)}">Back to the plans</a></p></section>')
    return _shell(market, title=f"Not subscribed — {market['name']}",
                  kicker="Intelligence feed", h1="Not subscribed",
                  sub="You left Stripe’s page before paying.",
                  inner=inner, front_href=front_href, about_href=about_href)


_HELP_CSS = """
<style>
.mm-v2 .v2-inq pre { background:var(--area-bg); border:1px solid var(--sidebar-border);
  border-radius:var(--r-xl); padding:var(--s-3) var(--s-4); overflow-x:auto;
  font-size:var(--fs-small); line-height:1.5; }
.mm-v2 .v2-inq h2 { margin-top:var(--s-6); }
.mm-v2 .v2-inq code { background:var(--area-bg); padding:0 4px; border-radius:4px; }
</style>
"""


def build_help_page(market: Dict[str, Any], *, front_href: str,
                    about_href: str) -> str:
    """The MCP setup guide. No secrets on it — the buyer supplies their
    own key from the confirmation mail — so it is public and cacheable."""
    mcp_url = (os.getenv("APP_URL") or "").rstrip("/") + "/mcp"
    subscribe = subscribe_href(market["id"])

    def block(code: str) -> str:
        return f"<pre>{esc(code)}</pre>"

    inner = (
        _HELP_CSS
        + "<section>"
        "<p>The MCP plan of the intelligence feed comes with a key that lets AI tools "
        "query our data directly: the news coverage, the vendors, the sentiment and "
        "the analyses behind the site. The key arrives in your confirmation mail. "
        "Wherever the examples below say <code>YOUR_KEY</code>, paste it in.</p>"
        f"<p>The server address is <code>{esc(mcp_url)}</code>. It speaks the Model "
        "Context Protocol over HTTP, and it authenticates with a bearer token in the "
        "<code>Authorization</code> header.</p>"

        "<h2>Check the key works</h2>"
        "<p>From any terminal with curl. A working key lists the available tools; a "
        "revoked or mistyped one gets a 401.</p>"
        + block('curl -X POST ' + mcp_url + ' \\\n'
                '  -H "Authorization: Bearer YOUR_KEY" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                '  -d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'')
        + "<h2>Claude Code</h2>"
        "<p>One command adds the server to your account:</p>"
        + block('claude mcp add --transport http aunoo ' + mcp_url + ' \\\n'
                '  --header "Authorization: Bearer YOUR_KEY"')
        + "<p>Then ask Claude Code anything about the market; it will call the tools "
        "itself. <code>claude mcp list</code> shows the connection.</p>"

        "<h2>Claude Desktop</h2>"
        "<p>Claude Desktop talks to local servers, so it needs the small "
        "<code>mcp-remote</code> bridge (Node.js). Add this to "
        "<code>claude_desktop_config.json</code> (Settings &gt; Developer &gt; Edit "
        "Config) and restart the app:</p>"
        + block('{\n  "mcpServers": {\n    "aunoo": {\n      "command": "npx",\n'
                '      "args": ["-y", "mcp-remote", "' + mcp_url + '",\n'
                '               "--header", "Authorization: Bearer YOUR_KEY"]\n'
                '    }\n  }\n}')
        + "<h2>Cursor</h2>"
        "<p>Add to <code>~/.cursor/mcp.json</code> (or the project's "
        "<code>.cursor/mcp.json</code>):</p>"
        + block('{\n  "mcpServers": {\n    "aunoo": {\n      "url": "' + mcp_url + '",\n'
                '      "headers": { "Authorization": "Bearer YOUR_KEY" }\n'
                '    }\n  }\n}')
        + "<h2>VS Code (Copilot)</h2>"
        "<p>Add to <code>.vscode/mcp.json</code> in your workspace:</p>"
        + block('{\n  "servers": {\n    "aunoo": {\n      "type": "http",\n'
                '      "url": "' + mcp_url + '",\n'
                '      "headers": { "Authorization": "Bearer YOUR_KEY" }\n'
                '    }\n  }\n}')
        + "<h2>Your own agent</h2>"
        "<p>Any MCP client library works the same way: streamable HTTP transport, "
        f"the URL <code>{esc(mcp_url)}</code>, and the header "
        "<code>Authorization: Bearer YOUR_KEY</code>. If your framework only "
        "speaks plain HTTP, the curl call above is the whole protocol surface — "
        "JSON-RPC 2.0 over POST.</p>"

        "<h2>If it stops working</h2>"
        "<p>A 401 means the key is no longer valid. Keys change when you re-issue "
        "your access from the payment success page, and they stop when a "
        "subscription ends — each new key arrives by mail and replaces the old one. "
        "If you cannot find the current key, reply to your confirmation mail and we "
        "will sort it out.</p>"
        f'<p>No key yet? The MCP plan is on <a href="{esc(subscribe)}">the plans page</a>.</p>'
        "</section>")
    return _shell(market, title=f"Connect your AI tools — {market['name']}",
                  kicker="Intelligence feed", h1="Connect your AI tools",
                  sub="How to point Claude, Cursor, VS Code or your own agents at "
                      "the MCP server.",
                  inner=inner, front_href=front_href, about_href=about_href)
