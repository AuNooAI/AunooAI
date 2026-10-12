"""A page address that redirects to a file is not read as a page
(aurascape.ai/security answers 301 to Security.png, 12 Oct 2026)."""

from __future__ import annotations

import asyncio

import httpx

from app.collectors import vendor_web_collector as vw


def _with(monkeypatch, content_type: str, body: bytes) -> None:
    def handler(request):
        return httpx.Response(200, headers={"content-type": content_type}, content=body)
    monkeypatch.setattr(vw, "_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)))


def test_an_image_is_refused(monkeypatch):
    _with(monkeypatch, "image/png", b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    result = asyncio.run(vw.fetch_page("https://example.com/security"))
    assert result.error == "not a web page (image/png)"
    assert result.changed is False and not result.text


def test_a_null_byte_in_a_page_is_dropped(monkeypatch):
    html = ("<html><head><title>Co\x00mpany</title></head><body><main><p>"
            + "We build AI security for agents. " * 20 + "\x00</p></main></body></html>")
    _with(monkeypatch, "text/html; charset=utf-8", html.encode())
    result = asyncio.run(vw.fetch_page("https://example.com/company"))
    assert "\x00" not in (result.text or "") and "\x00" not in (result.title or "")
