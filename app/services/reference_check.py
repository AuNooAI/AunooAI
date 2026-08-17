"""Probe report reference URLs: live, paywalled, blocked, or dead.

The release lint proves every claim traces to a cited article; this module
answers the next question — can the customer actually open the citation?
Each URL is fetched and classified:

    ok        reachable, the page loads
    paywall   loads but behind a paywall (schema.org isAccessibleForFree
              false, subscribe-to-read phrases, or a known hard-paywall
              publisher answering 401/403)
    blocked   the site refused this client with a bot check; the link may
              open fine in a real browser — verify by hand
    redirect  now lands on the site's homepage, which usually means the
              article was moved or removed
    dead      404/410, DNS failure, connection error, timeout, or 5xx

Network-bound (a few minutes for a full report corpus), so unlike
``report_lint`` it is wired as its own advisory step and can be disabled
with ``REPORT_REFERENCE_CHECK=0``. Findings only — nothing here blocks a
build. ``scripts/check_report_references.py`` is the CLI over this module.
"""
from __future__ import annotations

import asyncio
import logging as _logging
import re as _re
from urllib.parse import urlsplit as _urlsplit

_log = _logging.getLogger(__name__)

# Read this much of the body when looking for paywall/bot-check markers.
# Signals sit in the <head> or the first screen of markup; 200 KB is plenty.
_BODY_CAP = 200_000

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
}

# Publishers whose articles are behind a hard paywall. A 401/403 from these
# is a paywall, not a bot block.
PAYWALL_DOMAINS = {
    "wsj.com", "ft.com", "bloomberg.com", "economist.com",
    "theinformation.com", "sciencedirect.com", "nature.com",
    "link.springer.com", "onlinelibrary.wiley.com", "tandfonline.com",
    "ieee.org", "dl.acm.org",
}

# schema.org's machine-readable paywall marker, plus the phrases metered and
# hard paywalls actually render. Checked case-insensitively on the body.
_PAYWALL_BODY_RES = [
    _re.compile(r'"isAccessibleForFree"\s*:\s*(?:"?false"?)', _re.I),
    _re.compile(r"\b(?:subscribe|sign in|log in|register)\s+to\s+"
                r"(?:read|continue|keep reading|view)\b", _re.I),
    _re.compile(r"\bthis (?:article|content|story) is (?:for|available to|"
                r"reserved for) (?:our )?(?:subscribers|members)\b", _re.I),
    _re.compile(r"\balready a subscriber\b", _re.I),
    _re.compile(r"\bunlock (?:this|full) (?:article|story|access)\b", _re.I),
    _re.compile(r"\bcontinue reading (?:with|by)\b.{0,40}\bsubscri",
                _re.I | _re.S),
]

# Markers of an anti-bot interstitial, not a paywall.
_BOT_BLOCK_RES = [
    _re.compile(r"\bjust a moment\b", _re.I),                    # Cloudflare
    _re.compile(r"\bchecking your browser\b", _re.I),
    _re.compile(r"\bverify(?:ing)? (?:that )?you are (?:a )?human\b", _re.I),
    _re.compile(r"\benable javascript and cookies to continue\b", _re.I),
    _re.compile(r"\baccess denied\b.{0,200}\bpermission\b", _re.I | _re.S),
    _re.compile(r"px-captcha|_Incapsula_|distil_r_captcha|datadome", _re.I),
]

VERDICT_ORDER = ("ok", "paywall", "blocked", "redirect", "dead")


def registered_domain(host: str) -> str:
    """wsj.com from www.wsj.com — last two labels, enough for our lists."""
    parts = (host or "").lower().rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "").lower()


def classify(url: str, resp, body: str) -> tuple:
    """(verdict, note) for a completed httpx response."""
    status = resp.status_code
    final = str(resp.url)
    domain = registered_domain(_urlsplit(final).netloc)

    if status in (404, 410):
        return "dead", f"HTTP {status}"
    if status >= 500:
        return "dead", f"HTTP {status}"

    if status in (401, 402, 403, 451):
        if domain in PAYWALL_DOMAINS or status == 402:
            return "paywall", f"HTTP {status} from paywalled publisher"
        if any(rx.search(body) for rx in _BOT_BLOCK_RES):
            return "blocked", f"HTTP {status} bot check — may open in a real browser"
        return "blocked", f"HTTP {status}"

    if status == 429:
        return "blocked", "HTTP 429 rate-limited — retry later"

    # 2xx (or an odd 3xx httpx didn't follow).
    if any(rx.search(body) for rx in _BOT_BLOCK_RES):
        return "blocked", "bot-check page served with HTTP 200"
    for rx in _PAYWALL_BODY_RES:
        m = rx.search(body)
        if m:
            return "paywall", f"marker: {m.group(0)[:60]!r}"
    if domain in PAYWALL_DOMAINS:
        # Reachable page on a hard-paywall site with no marker found in the
        # first 200 KB — usually still metered. Flag softly.
        return "paywall", "known paywalled publisher (no marker seen)"

    # Redirected to the homepage or a bare section page: the original path
    # had content, the final one doesn't.
    orig_path = _urlsplit(url).path.strip("/")
    final_path = _urlsplit(final).path.strip("/")
    if orig_path and not final_path and registered_domain(
            _urlsplit(url).netloc) == domain:
        return "redirect", f"now lands on {final}"

    return "ok", f"HTTP {status}"


async def _probe(client, sem, url: str) -> dict:
    async with sem:
        try:
            body = ""
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_bytes():
                    body += chunk.decode("utf-8", errors="replace")
                    if len(body) >= _BODY_CAP:
                        break
                verdict, note = classify(url, resp, body)
                return {"url": url, "status": resp.status_code,
                        "final_url": str(resp.url),
                        "verdict": verdict, "note": note}
        except Exception as e:
            import httpx
            note = ("timeout" if isinstance(e, httpx.TimeoutException)
                    else f"{type(e).__name__}: {str(e)[:80]}")
            return {"url": url, "status": "", "final_url": "",
                    "verdict": "dead", "note": note}


async def check_urls(urls: list, *, concurrency: int = 8,
                     timeout: float = 15.0) -> list:
    """Probe every URL concurrently. Returns one dict per URL:
    ``{url, status, final_url, verdict, note}``, in input order."""
    import httpx
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True,
                                 timeout=timeout, verify=True) as client:
        return list(await asyncio.gather(
            *(_probe(client, sem, u) for u in urls)))


def summarize(results: list) -> dict:
    """Verdict → count, all five verdicts always present."""
    counts = {k: 0 for k in VERDICT_ORDER}
    for r in results:
        counts[r.get("verdict", "dead")] = counts.get(
            r.get("verdict", "dead"), 0) + 1
    return counts
