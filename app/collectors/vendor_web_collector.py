"""Vendor websites — feed discovery and page-state monitoring.

Two jobs, and they produce different things.

**Feeds** are the cheap path. A blog or newsroom with an RSS/Atom feed gets
registered as an ``rss_feeds`` row against the vendor's monitoring topic, and
the existing RSS collector takes it from there. Nothing new is needed to turn
those posts into articles.

**Pages** are for the parts of a site that never publish a feed — pricing,
customers, partners, docs, trust and careers. Their content is a *state*, not a
stream, so a fetch produces a ``bm_vendor_snapshots`` row, and what matters is
the difference between two of them.

Two rules keep page monitoring from generating noise:

- Extract the article text before hashing. A raw-HTML hash changes on every
  rotating testimonial, CSRF token, build id and cookie banner, so it reports
  a change on every fetch and means nothing.
- Compare on normalized lines. A reflowed paragraph is not news; a new
  enterprise tier on the pricing page is.

Conditional requests (``ETag`` / ``If-Modified-Since``) are used wherever the
server supports them, so an unchanged page usually costs a 304 and no body.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Aunoo Market Monitor (+https://aunoo.ai)"
HTTP_TIMEOUT = 20.0

# Sections worth watching on a vendor site, and what a change in each means.
# The daily set is where material change shows up; the rest move slowly enough
# that a weekly read is more resolution than the page has.
DAILY_PATHS = ("/blog", "/news", "/press", "/changelog", "/release-notes")
WEEKLY_PATHS = (
    "/pricing", "/customers", "/partners", "/docs", "/careers", "/jobs",
    "/security", "/trust", "/about", "/company", "/resources",
)

# Feed URLs to try when a page declares none. Cheap: a miss is one 404.
FEED_GUESSES = (
    "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml",
    "/blog/rss.xml", "/blog/feed", "/news/rss",
)

_FEED_LINK_RE = re.compile(
    r"""<link[^>]+type=["']application/(?:rss|atom)\+xml["'][^>]*>""",
    re.I,
)
_HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)
_SITEMAP_RE = re.compile(r"^\s*sitemap:\s*(\S+)", re.I | re.M)

# Lines that are furniture on every page. Dropping them before the diff is what
# stops "Accept all cookies" from being reported as a market development.
_BOILERPLATE = re.compile(
    r"^(cookie|accept all|we use cookies|privacy policy|terms of|all rights "
    r"reserved|©|copyright|subscribe|sign up|log ?in|menu|skip to)",
    re.I,
)


@dataclass
class DiscoveredSources:
    domain: str
    feeds: list[str] = field(default_factory=list)
    pages: list[dict[str, str]] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PageFetch:
    url: str
    status: int
    changed: bool
    content_hash: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    error: Optional[str] = None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def _root(domain: str) -> str:
    d = domain.strip().lower()
    if "://" not in d:
        d = "https://" + d
    p = urlparse(d)
    return f"https://{p.netloc or p.path}"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

async def discover_sources(domain: str, *, probe_pages: bool = True) -> DiscoveredSources:
    """Find a vendor's feeds and monitorable pages.

    Feeds are preferred over crawling everywhere they exist, so this looks at
    the homepage's declared feed links and ``robots.txt`` sitemaps before
    guessing at conventional paths.
    """
    root = _root(domain)
    out = DiscoveredSources(domain=urlparse(root).netloc)

    async with _client() as client:
        home_html = ""
        try:
            resp = await client.get(root)
            if resp.status_code < 400:
                home_html = resp.text
        except httpx.HTTPError as exc:
            out.errors.append(f"homepage: {exc}")

        for tag in _FEED_LINK_RE.findall(home_html or ""):
            href = _HREF_RE.search(tag)
            if href:
                out.feeds.append(urljoin(root, href.group(1)))

        try:
            robots = await client.get(urljoin(root, "/robots.txt"))
            if robots.status_code < 400:
                out.sitemaps = [m.strip() for m in _SITEMAP_RE.findall(robots.text)]
        except httpx.HTTPError as exc:
            out.errors.append(f"robots.txt: {exc}")

        if not out.feeds:
            found = await _probe(client, root, FEED_GUESSES, want_feed=True)
            out.feeds.extend(found)

        if probe_pages:
            for path in DAILY_PATHS:
                if await _exists(client, urljoin(root, path)):
                    out.pages.append({"url": urljoin(root, path), "cadence": "daily",
                                      "kind": _kind_for(path)})
            for path in WEEKLY_PATHS:
                if await _exists(client, urljoin(root, path)):
                    out.pages.append({"url": urljoin(root, path), "cadence": "weekly",
                                      "kind": _kind_for(path)})

    out.feeds = [f for f in dict.fromkeys(out.feeds) if not _is_noise_feed(f)]
    return out


# WordPress publishes a comments feed next to every content feed, and the
# discovery link tag advertises both. A vendor's comment stream is not their
# newsroom — registering it fills the corpus with reader replies.
_NOISE_FEED_MARKERS = (
    "/comments/feed", "comments/feed/", "?feed=comments", "/comment-feed",
)


def _is_noise_feed(url: str) -> bool:
    low = (url or "").lower()
    return any(marker in low for marker in _NOISE_FEED_MARKERS)


def _kind_for(path: str) -> str:
    p = path.strip("/").split("/")[0]
    return {
        "release-notes": "changelog", "jobs": "careers", "trust": "security",
        "company": "about",
    }.get(p, p or "page")


async def _exists(client: httpx.AsyncClient, url: str) -> bool:
    try:
        resp = await client.head(url)
        if resp.status_code == 405:  # HEAD not allowed — fall back to a GET
            resp = await client.get(url)
        return resp.status_code < 400
    except httpx.HTTPError:
        return False


async def _probe(
    client: httpx.AsyncClient, root: str, paths: Iterable[str], *, want_feed: bool,
) -> list[str]:
    found: list[str] = []
    for path in paths:
        url = urljoin(root, path)
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            continue
        if resp.status_code >= 400:
            continue
        body = resp.text[:2000].lstrip()
        if want_feed and not (body.startswith("<?xml") or "<rss" in body[:400].lower()
                              or "<feed" in body[:400].lower()):
            continue
        found.append(str(resp.url))
        await asyncio.sleep(0.2)  # courtesy spacing on one host
    return found


# ---------------------------------------------------------------------------
# Page state
# ---------------------------------------------------------------------------

def _html_title(html: str) -> Optional[str]:
    """The page's own ``<title>``.

    trafilatura's metadata title is absent on most vendor pages — all 91 stored
    page snapshots had a null title — which left the pages dataset showing a
    URL and nothing a reader could recognise. The tag itself is nearly always
    there.
    """
    import html as html_mod

    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
    if not m:
        return None
    title = re.sub(r"<[^>]+>", "", m.group(1))
    title = re.sub(r"\s+", " ", html_mod.unescape(title)).strip()
    return title[:300] or None


def extract_text(html: str) -> tuple[Optional[str], Optional[str]]:
    """``(title, main text)`` with navigation and furniture removed.

    Falls back to a crude tag strip when the extractor declines, because a page
    we cannot extract still deserves a stable hash rather than being treated as
    permanently changed.
    """
    try:
        import trafilatura

        text = trafilatura.extract(
            html, include_comments=False, include_tables=True,
            favor_precision=True,
        )
        meta = trafilatura.extract_metadata(html)
        title = getattr(meta, "title", None) if meta else None
        if text:
            return title or _html_title(html), text
    except Exception:  # noqa: BLE001 — extraction is best-effort
        logger.debug("trafilatura extraction failed", exc_info=True)

    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                      flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return _html_title(html), stripped or None


def normalize_lines(text: str | None) -> list[str]:
    """Comparable lines: trimmed, de-blanked, furniture dropped."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or _BOILERPLATE.match(line):
            continue
        out.append(line)
    return out


def hash_text(text: str | None) -> str:
    return hashlib.sha256("\n".join(normalize_lines(text)).encode()).hexdigest()


async def fetch_page(
    url: str, *, etag: str | None = None, last_modified: str | None = None,
    prior_hash: str | None = None,
) -> PageFetch:
    """Conditionally fetch a page and report whether its content changed."""
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        async with _client() as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return PageFetch(url=url, status=0, changed=False, error=str(exc))

    if resp.status_code == 304:
        # The cheapest possible answer, and an unambiguous one.
        return PageFetch(url=url, status=304, changed=False, etag=etag,
                         last_modified=last_modified)
    if resp.status_code >= 400:
        return PageFetch(url=url, status=resp.status_code, changed=False,
                         error=f"HTTP {resp.status_code}")

    title, text = extract_text(resp.text)
    digest = hash_text(text)
    return PageFetch(
        url=str(resp.url),
        status=resp.status_code,
        changed=(prior_hash is None or digest != prior_hash),
        content_hash=digest,
        text=text,
        title=title,
        etag=resp.headers.get("etag"),
        last_modified=resp.headers.get("last-modified"),
    )


def diff_pages(old_text: str | None, new_text: str | None, *,
               max_lines: int = 40) -> dict[str, Any]:
    """What actually changed between two page states.

    Returns added and removed lines with the counts, so an event can quote the
    evidence rather than assert that "the pricing page changed". A diff whose
    added and removed sets are both empty means the change was reflow, and the
    caller should treat it as no change at all.
    """
    old_lines = normalize_lines(old_text)
    new_lines = normalize_lines(new_text)
    added: list[str] = []
    removed: list[str] = []
    for line in difflib.unified_diff(old_lines, new_lines, n=0, lineterm=""):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:].strip())

    # A line that merely moved is not a change. Dropping the intersection is
    # what keeps a re-ordered feature list from reading as a product launch.
    added_set, removed_set = set(added), set(removed)
    moved = added_set & removed_set
    added = [line for line in added if line not in moved]
    removed = [line for line in removed if line not in moved]

    return {
        "added": added[:max_lines],
        "removed": removed[:max_lines],
        "added_count": len(added),
        "removed_count": len(removed),
        "moved_count": len(moved),
        "material": bool(added or removed),
    }
