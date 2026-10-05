"""Get the full dataset: the subscription pages and the Stripe webhook.

Included from market_monitor_routes so it rides on the same prefix and
the module's enable switch, exactly like the inquiry routes. Nothing here
imports that module; the helpers live in app/services/market_subscription.py.
"""

import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.routes.market_inquiry_routes import _links
from app.services import market_subscription as msub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market subscription"])

_NO_STORE = {"Cache-Control": "no-store"}


def _market_or_404(c, market_id: int, *, public_only: bool = True):
    market = msub.load_market(c, market_id, public_only=public_only)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


@router.get("/markets/{market_id}/subscribe", response_class=HTMLResponse)
async def subscribe_form(market_id: int, request: Request):
    front, about = _links(request, market_id)

    def _work():
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id)
            totals = msub.roster_counts(c, market_id)
        finally:
            c.close()
        if not msub.is_configured():
            raise HTTPException(status_code=503, detail="Subscriptions are not available right now")
        return msub.build_subscribe_page(
            market, front_href=front, about_href=about, totals=totals,
            action=f"{msub.subscribe_href(market_id)}/checkout")

    html = await asyncio.to_thread(_work)
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@router.post("/markets/{market_id}/subscribe/checkout")
async def subscribe_checkout(market_id: int, request: Request,
                             plan: str = Form(...),
                             name: str = Form(""),
                             email: str = Form(...),
                             website: str = Form("")):
    """Validate, write the row, send the buyer to Stripe."""
    if website.strip():
        # The honeypot field is hidden from people; a bot filled it.
        return Response(status_code=204)
    front, about = _links(request, market_id)
    values = {"plan": plan, "name": name.strip()[:200], "email": email.strip().lower()}

    def _page(error: str, status: int):
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id)
            totals = msub.roster_counts(c, market_id)
        finally:
            c.close()
        return HTMLResponse(msub.build_subscribe_page(
            market, front_href=front, about_href=about, error=error, values=values,
            totals=totals, action=f"{msub.subscribe_href(market_id)}/checkout"),
            status_code=status, headers=_NO_STORE)

    if plan not in msub.PLANS:
        return await asyncio.to_thread(_page, "Pick a plan.", 422)
    if not values["name"]:
        return await asyncio.to_thread(_page, "Your name is needed for the account.", 422)
    if not msub.EMAIL_RE.match(values["email"]):
        return await asyncio.to_thread(_page, "That email address does not look right.", 422)
    if not msub.is_configured():
        return await asyncio.to_thread(_page, "Subscriptions are not available right now.", 503)

    ip, ua, base = msub.client_ip(request), msub.user_agent(request), msub.base_url(request)

    def _work():
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id)
            if msub.too_many_today(c, ip):
                raise HTTPException(status_code=429,
                                    detail="Too many attempts from this address today")
            return msub.create_session(c, market, plan=plan, name=values["name"],
                                       email=values["email"], ip=ip, ua=ua, base=base)
        finally:
            c.close()

    try:
        url = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — Stripe or network
        logger.exception("subscription checkout failed for market %s", market_id)
        return await asyncio.to_thread(
            _page, "Stripe did not answer. Nothing was charged; please try again in a minute.", 502)
    return RedirectResponse(url, status_code=303, headers=_NO_STORE)


@router.get("/markets/{market_id}/subscribe/done", response_class=HTMLResponse)
async def subscribe_done(market_id: int, request: Request,
                         session_id: str = Query(..., min_length=8, max_length=255)):
    """Stripe sends the buyer back here. Confirm with Stripe, activate the
    row if the webhook has not already, and show the credentials — once —
    when this request is the one that minted them."""
    front, about = _links(request, market_id)

    def _work():
        from datetime import datetime, timedelta, timezone

        session = msub.retrieve_session(session_id)
        meta = session.get("metadata") or {}
        if meta.get("app") != msub.META_APP or str(meta.get("market_id")) != str(market_id):
            raise HTTPException(status_code=404, detail="Unknown session")
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id, public_only=False)
            row, access_token, mcp_key = msub.activate(c, session)
            paid = session.get("payment_status") == "paid"
            # The self-healing case: the webhook won the race but its mail
            # never went out, so the plaintext is lost. The buyer holding
            # the success URL is proof enough — rotate and show. The grace
            # window keeps us from rotating under a webhook whose mail is
            # still in flight.
            if (row and paid and not access_token and not row.get("notified_buyer")):
                activated = row.get("activated_at")
                if activated and activated.tzinfo is None:
                    activated = activated.replace(tzinfo=timezone.utc)
                if activated and (datetime.now(timezone.utc) - activated
                                  > timedelta(minutes=3)):
                    row, access_token, mcp_key = msub.reissue(c, session)
            if row and access_token:
                msub.notify(c, row, market, access_token=access_token, mcp_key=mcp_key)
            return msub.build_done_page(
                market, row, paid=paid, access_token=access_token, mcp_key=mcp_key,
                front_href=front, about_href=about,
                reissue_action=f"{msub.subscribe_href(market_id)}/reissue",
                session_id=session_id)
        finally:
            c.close()

    try:
        html = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("subscription done page failed for session %s", session_id)
        raise HTTPException(status_code=502, detail="Stripe did not answer; try again in a minute")
    return HTMLResponse(html, headers=_NO_STORE)


@router.post("/markets/{market_id}/subscribe/reissue", response_class=HTMLResponse)
async def subscribe_reissue(market_id: int, request: Request,
                            session_id: str = Form(..., min_length=8, max_length=255)):
    """Rotate the credentials for a live subscription and show the new
    ones. The Checkout session id from Stripe's success redirect is the
    proof of ownership; the old link and key stop working."""
    front, about = _links(request, market_id)

    def _work():
        session = msub.retrieve_session(session_id)
        meta = session.get("metadata") or {}
        if meta.get("app") != msub.META_APP or str(meta.get("market_id")) != str(market_id):
            raise HTTPException(status_code=404, detail="Unknown session")
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id, public_only=False)
            row, access_token, mcp_key = msub.reissue(c, session)
            if row and access_token:
                msub.notify(c, row, market, access_token=access_token, mcp_key=mcp_key)
            return msub.build_done_page(
                market, row, paid=bool(row and access_token),
                access_token=access_token, mcp_key=mcp_key,
                front_href=front, about_href=about)
        finally:
            c.close()

    try:
        html = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("subscription reissue failed for session %s", session_id)
        raise HTTPException(status_code=502, detail="Stripe did not answer; try again in a minute")
    return HTMLResponse(html, headers=_NO_STORE)


@router.get("/markets/{market_id}/subscribe/help", response_class=HTMLResponse)
async def subscribe_help(market_id: int, request: Request):
    """The MCP setup guide. Public and secret-free: buyers paste their own
    key from the mail into the copy-paste configs."""
    front, about = _links(request, market_id)

    def _work():
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id)
        finally:
            c.close()
        return msub.build_help_page(market, front_href=front, about_href=about)

    html = await asyncio.to_thread(_work)
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@router.get("/markets/{market_id}/subscribe/cancelled", response_class=HTMLResponse)
async def subscribe_cancelled(market_id: int, request: Request):
    front, about = _links(request, market_id)

    def _work():
        c = msub.conn()
        try:
            market = _market_or_404(c, market_id)
        finally:
            c.close()
        return msub.build_cancelled_page(market, retry_href=msub.subscribe_href(market_id),
                                         front_href=front, about_href=about)

    return HTMLResponse(await asyncio.to_thread(_work), headers=_NO_STORE)


@router.post("/markets/{market_id}/subscribe/webhook")
async def subscribe_webhook(market_id: int, request: Request):
    """Stripe's side of the story: activation and the lifecycle. The
    account is shared with saas.aunoo.ai and the analyst-call flow, so
    anything that is not ours gets a 200 and nothing else."""
    import json

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = msub.event_from_webhook(payload, signature)
    except Exception:  # noqa: BLE001 — bad signature or malformed body
        logger.warning("subscription webhook: signature verification failed")
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})

    checkout_events = ("checkout.session.completed",
                       "checkout.session.async_payment_succeeded")
    lifecycle_events = ("customer.subscription.updated",
                        "customer.subscription.deleted")
    if event.type not in checkout_events + lifecycle_events:
        return {"ok": True, "ignored": event.type}
    obj = json.loads(str(event.data.object))

    def _work():
        c = msub.conn()
        try:
            if event.type in checkout_events:
                row, access_token, mcp_key = msub.activate(c, obj)
                if row is None:
                    return {"ok": True, "ignored": "not ours"}
                if access_token:
                    market = msub.load_market(c, int(row["market_id"]), public_only=False) or \
                        {"id": row["market_id"], "name": "the market"}
                    msub.notify(c, row, market, access_token=access_token, mcp_key=mcp_key)
                return {"ok": True, "id": int(row["id"]), "status": row["status"]}
            moved = msub.apply_lifecycle(
                c, obj, deleted=event.type == "customer.subscription.deleted")
            return {"ok": True, "status": moved or "unchanged"}
        finally:
            c.close()

    return await asyncio.to_thread(_work)
