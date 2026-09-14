"""Fetch each market vendor's mark and store it on ``bw_brands.logo_data``.

For each vendor with a website: read the site once and try, in order, the
apple-touch-icon, an icon link, og:image and /favicon.ico; take the first
that is 32 px or larger and square-ish, or an SVG. With nothing usable on the
site, fall back to Google's favicon service for the domain, unless it returns
its default globe. The mark is stored as a data URI: a 64 px PNG (an SVG is
rasterised), so the page can draw it without an external request.

Dry by default: prints what would be stored. ``--apply`` writes. A vendor
that already has a mark is skipped unless ``--refresh``.

    .venv/bin/python scripts/fetch_vendor_logos.py --market 2 [--apply] [--refresh]
"""
import argparse
import base64
import hashlib
import io
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; AunooLogoFetch/1.0)"}
SIZE = 64
MIN_PX = 32
# Google's favicon service answers a domain it does not know with one default
# globe; its bytes are constant, so the first fetch of a nonsense domain
# gives the fingerprint to skip.
_GOOGLE = "https://www.google.com/s2/favicons?domain={domain}&sz=64"


def _load_env() -> None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _candidates(html: str, base: str):
    out = []
    for m in re.finditer(r"<link[^>]+>", html, re.I):
        tag = m.group(0)
        rel = (re.search(r'rel=["\']([^"\']+)', tag, re.I) or [None, ""])[1].lower()
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if not href:
            continue
        if "apple-touch-icon" in rel:
            out.append(("apple-touch-icon", urljoin(base, href.group(1))))
        elif "icon" in rel:
            out.append(("icon", urljoin(base, href.group(1))))
    og = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
          or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I))
    if og:
        out.append(("og:image", urljoin(base, og.group(1))))
    out.append(("favicon.ico", urljoin(base, "/favicon.ico")))
    # The apple-touch-icon and any sized icon first; og:image is a banner more
    # often than a mark, so it is the last resort before the favicon.
    order = {"apple-touch-icon": 0, "icon": 1, "favicon.ico": 2, "og:image": 3}
    return sorted(out, key=lambda c: order[c[0]])


def _to_png_data_uri(content: bytes, is_svg: bool) -> str | None:
    """A 64 px PNG data URI from image bytes, or None when unusable."""
    try:
        if is_svg:
            import cairosvg
            content = cairosvg.svg2png(bytestring=content, output_width=SIZE, output_height=SIZE)
        im = Image.open(io.BytesIO(content))
        if not is_svg:
            w, h = im.size
            if min(w, h) < MIN_PX or not (0.75 <= w / max(h, 1) <= 1.34):
                return None
        im = im.convert("RGBA")
        # Fit into the square on a transparent ground, centred.
        im.thumbnail((SIZE, SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001 — a mark we cannot decode is a mark we do not have
        return None


def _fetch(url: str):
    try:
        r = requests.get(url, headers=UA, timeout=12, allow_redirects=True)
        if r.status_code != 200 or not r.content:
            return None, None
        is_svg = "svg" in r.headers.get("content-type", "") or url.lower().endswith(".svg")
        return r.content, is_svg
    except Exception:  # noqa: BLE001
        return None, None


def _google_default_fingerprint() -> str | None:
    content, _ = _fetch(_GOOGLE.format(domain="no-such-domain-aunoo-check.invalid"))
    return hashlib.sha1(content).hexdigest() if content else None


def find_mark(site: str, google_default: str | None):
    """(data_uri, source) for one site, or (None, reason)."""
    base = site if site.startswith("http") else f"https://{site}"
    html, final = "", base
    try:
        r = requests.get(base, headers=UA, timeout=15, allow_redirects=True)
        html, final = r.text, r.url
    except Exception as exc:  # noqa: BLE001
        reason = f"site unreachable: {str(exc)[:60]}"
    else:
        reason = "no usable image on the site"
        for kind, url in _candidates(html, final):
            content, is_svg = _fetch(url)
            if not content:
                continue
            uri = _to_png_data_uri(content, is_svg)
            if uri:
                return uri, url
    domain = urlparse(final or base).netloc.replace("www.", "")
    content, _ = _fetch(_GOOGLE.format(domain=domain))
    if content and (google_default is None or hashlib.sha1(content).hexdigest() != google_default):
        uri = _to_png_data_uri(content, False)
        if uri:
            return uri, _GOOGLE.format(domain=domain)
    return None, reason


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="re-fetch vendors that already have a mark")
    args = ap.parse_args()
    _load_env()
    from app.database import get_database_instance

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        rows = [dict(r) for r in conn.execute(text("""
            SELECT b.id AS brand_id, b.display_name AS vendor, b.logo_data IS NOT NULL AS has_mark,
                   COALESCE(MAX(COALESCE(vi.display_value, vi.normalized_value)) FILTER (WHERE vi.kind = 'website_url'),
                            MAX(COALESCE(vi.display_value, vi.normalized_value)) FILTER (WHERE vi.kind = 'domain')) AS site
              FROM bw_market_brands mb
              JOIN bw_brands b ON b.id = mb.brand_id
              LEFT JOIN bw_vendor_identifiers vi ON vi.brand_id = mb.brand_id
             WHERE mb.market_id = :m AND mb.role <> 'excluded'
             GROUP BY b.id, b.display_name, b.logo_data ORDER BY b.display_name
        """), {"m": args.market}).mappings().all()]
    finally:
        conn.close()
    todo = [r for r in rows if r["site"] and (args.refresh or not r["has_mark"])]
    print(f"vendors: {len(rows)}; to fetch: {len(todo)}; without a website: "
          f"{sum(1 for r in rows if not r['site'])}")
    google_default = _google_default_fingerprint()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda r: (r, *find_mark(r["site"], google_default)), todo))
    found = [(r, uri, src) for r, uri, src in results if uri]
    for r, uri, src in results:
        print(f'{"mark" if uri else "none":5} {r["vendor"]:28} {(src if uri else src)[:80]}')
    print(f"found: {len(found)} of {len(todo)}; "
          f"bytes stored: {sum(len(u) for _, u, _ in found):,}")
    if not args.apply:
        print("dry run; add --apply to write")
        return 0
    conn = db._temp_get_connection()
    try:
        now = datetime.now(timezone.utc)
        for r, uri, src in found:
            conn.execute(text("""
                UPDATE bw_brands SET logo_data = :d, logo_source = :s, logo_fetched_at = :t
                 WHERE id = :b
            """), {"d": uri, "s": src, "t": now, "b": r["brand_id"]})
        conn.commit()
        print(f"stored: {len(found)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
