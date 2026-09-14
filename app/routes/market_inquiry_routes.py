"""Schedule an inquiry: the paid-call pages and the Stripe webhook.

Included from market_monitor_routes so it rides on the same prefix and the
module's enable switch. Nothing here imports that module: the small helpers
it would need live in app/services/market_inquiry.py, or the import would
be circular.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.services import market_inquiry as inq

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market inquiry"])

_NO_STORE = {"Cache-Control": "no-store"}


def _links(request: Request, market_id: int):
    """Front page and About links as they should read on this host. On
    aisocnews.com the front page is ``/``; on the app host it is the
    report route."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    app_host = ""
    try:
        from urllib.parse import urlparse
        import os
        app_host = (urlparse(os.getenv("APP_URL") or "").hostname or "").lower()
    except Exception:  # noqa: BLE001
        pass
    if host and host != app_host and not host.startswith("127.") and host != "localhost":
        return "/", "/?view=v2&page=about"
    report = f"/api/market-monitor/markets/{int(market_id)}/report.html"
    return f"{report}?view=v2", f"{report}?view=v2&page=about"


def _market_or_404(c, market_id: int, *, public_only: bool = True):
    market = inq.load_market(c, market_id, public_only=public_only)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


@router.get("/markets/{market_id}/inquiry", response_class=HTMLResponse)
async def inquiry_form(market_id: int, request: Request):
    front, about = _links(request, market_id)

    def _work():
        c = inq.conn()
        try:
            market = _market_or_404(c, market_id)
        finally:
            c.close()
        if not inq.is_configured():
            raise HTTPException(status_code=503, detail="Booking is not available right now")
        return inq.build_inquiry_page(
            market, front_href=front, about_href=about,
            action=f"{inq.inquiry_href(market_id)}/checkout")

    html = await asyncio.to_thread(_work)
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@router.post("/markets/{market_id}/inquiry/checkout")
async def inquiry_checkout(market_id: int, request: Request,
                           minutes: int = Form(...),
                           subject: str = Form(""),
                           name: str = Form(""),
                           email: str = Form(...),
                           website: str = Form("")):
    """Validate, write the row, send the buyer to Stripe."""
    if website.strip():
        # The honeypot field is hidden from people; a bot filled it.
        return Response(status_code=204)
    front, about = _links(request, market_id)
    values = {"minutes": minutes, "subject": subject.strip()[:2000],
              "name": name.strip()[:200], "email": email.strip().lower()}

    def _page(error: str, status: int):
        c = inq.conn()
        try:
            market = _market_or_404(c, market_id)
        finally:
            c.close()
        return HTMLResponse(inq.build_inquiry_page(
            market, front_href=front, about_href=about, error=error, values=values,
            action=f"{inq.inquiry_href(market_id)}/checkout"),
            status_code=status, headers=_NO_STORE)

    if minutes not in inq.OPTIONS:
        return await asyncio.to_thread(_page, "Pick 30 or 60 minutes.", 422)
    if not values["name"]:
        return await asyncio.to_thread(_page, "Your name is needed for the calendar invitation.", 422)
    if not inq.EMAIL_RE.match(values["email"]):
        return await asyncio.to_thread(_page, "That email address does not look right.", 422)
    if not inq.is_configured():
        return await asyncio.to_thread(_page, "Booking is not available right now.", 503)

    ip, ua, base = inq.client_ip(request), inq.user_agent(request), inq.base_url(request)

    def _work():
        c = inq.conn()
        try:
            market = _market_or_404(c, market_id)
            if inq.too_many_today(c, ip):
                raise HTTPException(status_code=429,
                                    detail="Too many attempts from this address today")
            return inq.create_session(c, market, minutes=minutes, subject=values["subject"],
                                      name=values["name"], email=values["email"],
                                      ip=ip, ua=ua, base=base)
        finally:
            c.close()

    try:
        url = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — Stripe or network
        logger.exception("inquiry checkout failed for market %s", market_id)
        return await asyncio.to_thread(
            _page, "Stripe did not answer. Nothing was charged; please try again in a minute.", 502)
    return RedirectResponse(url, status_code=303, headers=_NO_STORE)


@router.get("/markets/{market_id}/inquiry/done", response_class=HTMLResponse)
async def inquiry_done(market_id: int, request: Request,
                       session_id: str = Query(..., min_length=8, max_length=255)):
    """Stripe sends the buyer back here. Confirm with Stripe, mark the row
    paid if the webhook has not already, and show the booking link."""
    front, about = _links(request, market_id)

    def _work():
        session = inq.retrieve_session(session_id)
        meta = session.get("metadata") or {}
        if meta.get("app") != inq.META_APP or str(meta.get("market_id")) != str(market_id):
            raise HTTPException(status_code=404, detail="Unknown session")
        c = inq.conn()
        try:
            market = _market_or_404(c, market_id, public_only=False)
            row = inq.mark_paid(c, session)
            paid = session.get("payment_status") == "paid"
            if row and paid:
                inq.notify(c, row, market)
            return inq.build_done_page(market, row, paid=paid,
                                       front_href=front, about_href=about)
        finally:
            c.close()

    try:
        html = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("inquiry done page failed for session %s", session_id)
        raise HTTPException(status_code=502, detail="Stripe did not answer; try again in a minute")
    return HTMLResponse(html, headers=_NO_STORE)


@router.get("/markets/{market_id}/inquiry/cancelled", response_class=HTMLResponse)
async def inquiry_cancelled(market_id: int, request: Request):
    front, about = _links(request, market_id)

    def _work():
        c = inq.conn()
        try:
            market = _market_or_404(c, market_id)
        finally:
            c.close()
        return inq.build_cancelled_page(market, retry_href=inq.inquiry_href(market_id),
                                        front_href=front, about_href=about)

    return HTMLResponse(await asyncio.to_thread(_work), headers=_NO_STORE)


@router.post("/markets/{market_id}/inquiry/webhook")
async def inquiry_webhook(market_id: int, request: Request):
    """Stripe's side of the story. Signature-verified; a session that is not
    ours (the account is shared with saas.aunoo.ai) gets a 200 and nothing
    else, so Stripe does not retry it."""
    import json

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = inq.event_from_webhook(payload, signature)
    except Exception:  # noqa: BLE001 — bad signature or malformed body
        logger.warning("inquiry webhook: signature verification failed")
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})

    if event.type not in ("checkout.session.completed",
                          "checkout.session.async_payment_succeeded"):
        return {"ok": True, "ignored": event.type}
    session = json.loads(str(event.data.object))

    def _work():
        c = inq.conn()
        try:
            row = inq.mark_paid(c, session)
            if row is None:
                return {"ok": True, "ignored": "not ours"}
            if int(row.get("market_id") or 0) != int(market_id):
                logger.warning("inquiry %s: webhook path market %s differs from row market %s",
                               row["id"], market_id, row.get("market_id"))
            market = inq.load_market(c, int(row["market_id"]), public_only=False) or \
                {"id": row["market_id"], "name": "the market"}
            inq.notify(c, row, market)
            return {"ok": True, "id": int(row["id"]), "status": row["status"]}
        finally:
            c.close()

    return await asyncio.to_thread(_work)
