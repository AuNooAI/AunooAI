"""Restore the text of social posts the news analyzer rewrote.

A social post that went through the news enrichment pipeline had its `summary`
replaced by the analyzer's précis and its original text dropped. The post still
exists on the platform, so this re-fetches it by id (Bluesky public API for
Bluesky, xpoz get_posts_by_ids / get_post_with_comments for X, Instagram,
TikTok and Reddit) and writes the text back through the same translation step
a fresh collection uses (`english_fields`), so `summary` is the post in English
and `original_summary` the post as written when it was not English. Sentiment,
relevance and category are left as they are.

Run inside a tenant tree with that tenant's venv:

    .venv/bin/python scripts/restore_social_text.py --dry-run
    .venv/bin/python scripts/restore_social_text.py --limit 50
    .venv/bin/python scripts/restore_social_text.py

Selects rows where the analyzer ran (category IS NOT NULL) and no original
text is stored. Posts that no longer exist on the platform are reported and
left alone.
"""
import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.getcwd(), ".env"))

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services.social_engagement_refresh import (  # noqa: E402
    _BskyClient, _BSKY_APPVIEW, _BSKY_BATCH, _BSKY_URL, _XPOZ_BATCH, _as_dict,
    _external_id_of, _platform_of)
from app.services.social_sources import social_src_sql  # noqa: E402
from app.utils.title_translation import english_fields  # noqa: E402
from app.collectors.xpoz_collector import _clean as _xpoz_clean  # noqa: E402

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("restore_social_text")

_XPOZ_TEXT_FIELDS = {
    "twitter": ["id", "text"],
    "instagram": ["id", "caption"],
    "tiktok": ["id", "description"],
}


def _bsky_texts(client: _BskyClient, urls: List[str]) -> Dict[str, Tuple[str, str]]:
    """url -> (handle, text) from the public AppView."""
    at_by_url: Dict[str, str] = {}
    for u in urls:
        m = _BSKY_URL.search(u or "")
        if not m:
            continue
        did = client._did(m.group(1))
        if did:
            at_by_url[u] = f"at://{did}/app.bsky.feed.post/{m.group(2)}"
    out: Dict[str, Tuple[str, str]] = {}
    items = list(at_by_url.items())
    for i in range(0, len(items), _BSKY_BATCH):
        chunk = items[i:i + _BSKY_BATCH]
        try:
            r = client._http.get(f"{_BSKY_APPVIEW}/app.bsky.feed.getPosts",
                                 params=[("uris", at_uri) for _, at_uri in chunk])
            if r.status_code != 200:
                log.warning("bsky getPosts HTTP %s", r.status_code)
                continue
            posts = {p.get("uri"): p for p in r.json().get("posts", [])}
            for url, at_uri in chunk:
                p = posts.get(at_uri)
                if not p:
                    continue
                body = ((p.get("record") or {}).get("text") or "").strip()
                handle = (p.get("author") or {}).get("handle") or ""
                if body:
                    out[url] = (handle, body)
        except Exception as e:
            log.warning("bsky getPosts batch failed: %s", e)
    return out


def _xpoz_texts(client, platform: str, ids: List[str]) -> Dict[str, str]:
    """external_id -> text via xpoz."""
    out: Dict[str, str] = {}
    if platform == "reddit":
        for pid in ids:
            try:
                res = client.reddit.get_post_with_comments(
                    pid, post_fields=["id", "title", "selftext"], comment_fields=["id"])
                p = getattr(res, "post", res)
                title = (getattr(p, "title", None) or "").strip()
                body = _xpoz_clean(getattr(p, "selftext", None) or "") or _xpoz_clean(title)
                if body:
                    out[str(pid)] = body
            except Exception as e:
                log.warning("xpoz reddit fetch failed for %s: %s", pid, e)
        return out
    ns = getattr(client, platform, None)
    if ns is None or not hasattr(ns, "get_posts_by_ids"):
        return out
    field = _XPOZ_TEXT_FIELDS.get(platform, ["id"])[-1]
    for i in range(0, len(ids), _XPOZ_BATCH):
        chunk = ids[i:i + _XPOZ_BATCH]
        try:
            posts = ns.get_posts_by_ids(chunk, fields=_XPOZ_TEXT_FIELDS.get(platform, ["id"]))
        except Exception as e:
            log.warning("xpoz %s get_posts_by_ids failed: %s", platform, e)
            continue
        for p in posts or []:
            pid = str(getattr(p, "id", "") or "")
            body = _xpoz_clean(getattr(p, field, None) or "")
            if pid and body:
                out[pid] = body
    return out


def _social_title(platform: str, handle: Optional[str], body: str) -> str:
    """The title a fresh collection would have given the post."""
    if platform == "bluesky" and handle:
        return f"@{handle}: {body[:300]}"
    return body[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = get_database_instance()
    q = f"""
        SELECT uri, news_source, social_meta, title, summary
        FROM articles
        WHERE {social_src_sql('news_source')}
          AND category IS NOT NULL
          AND original_summary IS NULL
          -- only rows that still carry the analyzer's précis; a restored
          -- English post keeps original_summary NULL and must not be re-fetched
          AND summary ~ '^(A |An |The |This )?(Twitter|Reddit|Instagram|TikTok|Bluesky|social media|user|post|X user|Japanese|German|French)'
        ORDER BY publication_date DESC
        {'LIMIT ' + str(args.limit) if args.limit else ''}
    """
    rows = db.facade._execute_with_rollback(text(q)).fetchall()
    print(f"candidates: {len(rows)}")
    if not rows:
        return 0

    by_platform: Dict[str, List[Tuple[str, str]]] = {}
    bsky_urls: List[str] = []
    for uri, news_source, meta, _t, _s in rows:
        meta = _as_dict(meta)
        platform = _platform_of(news_source, meta)
        if platform == "bluesky":
            bsky_urls.append(uri)
            continue
        ext = _external_id_of(platform or "", uri, meta) if platform else None
        if platform and ext:
            by_platform.setdefault(platform, []).append((uri, ext))

    fetched: Dict[str, Tuple[str, Optional[str], str]] = {}  # uri -> (platform, handle, body)
    if bsky_urls:
        c = _BskyClient()
        try:
            for url, (handle, body) in _bsky_texts(c, bsky_urls).items():
                fetched[url] = ("bluesky", handle, body)
        finally:
            c.close()
    api_key = os.getenv("XPOZ_API_KEY") or os.getenv("PROVIDER_XPOZ_API_KEY")
    if by_platform and api_key:
        from xpoz import XpozClient
        client = XpozClient(api_key, check_update=False, timeout=60)
        try:
            for platform, entries in by_platform.items():
                texts = _xpoz_texts(client, platform, [e[1] for e in entries])
                for uri, ext in entries:
                    body = texts.get(str(ext))
                    if body:
                        fetched[uri] = (platform, None, body)
                print(f"{platform}: fetched {sum(1 for u, _ in entries if u in fetched)}/{len(entries)}")
        finally:
            client.close()
    elif by_platform:
        print("no XPOZ_API_KEY; xpoz platforms skipped")
    print(f"bluesky: fetched {sum(1 for u in bsky_urls if u in fetched)}/{len(bsky_urls)}")

    restored = translated = 0
    for uri, news_source, meta, old_title, old_summary in rows:
        got = fetched.get(uri)
        if not got:
            continue
        platform, handle, body = got
        article = {"title": _social_title(platform, handle, body), "summary": body}
        english_fields(article)  # translates in place when not English; sets original_*
        if args.dry_run:
            print(f"- {uri}\n    was: {old_summary[:110]!r}\n    now: {article['summary'][:110]!r}"
                  + (f"\n    orig: {article['original_summary'][:80]!r}" if article.get('original_summary') else ""))
        else:
            db.facade._execute_with_rollback(text(
                "UPDATE articles SET title = :t, summary = :s, original_title = :ot, original_summary = :os WHERE uri = :u"
            ), {"t": article["title"], "s": article["summary"], "ot": article.get("original_title"),
                "os": article.get("original_summary"), "u": uri})
        restored += 1
        translated += 1 if article.get("original_summary") else 0
    print(f"{'would restore' if args.dry_run else 'restored'}: {restored} (translated: {translated}); "
          f"not found on platform: {len(rows) - restored}")

    # Second pass: posts that were translated at insert (original_summary kept)
    # and then rewritten by the analyzer. The original is still in the row, so
    # no platform call is needed: translate it again and put the text back.
    # Selected by the précis shape of the summary, so a genuine post whose text
    # happens to match is merely re-translated from its own original.
    rows2 = db.facade._execute_with_rollback(text(f"""
        SELECT uri, news_source, social_meta, title, original_summary
        FROM articles
        WHERE {social_src_sql('news_source')}
          AND category IS NOT NULL
          AND original_summary IS NOT NULL
          AND summary ~ '^(A |An |The |This )?(Twitter|Reddit|Instagram|TikTok|Bluesky|social media|user|post|X user|Japanese|German|French)'
        {'LIMIT ' + str(args.limit) if args.limit else ''}
    """)).fetchall()
    print(f"second pass (rewritten after translation): {len(rows2)}")
    fixed = 0
    for uri, news_source, meta, old_title, original in rows2:
        meta = _as_dict(meta)
        platform = _platform_of(news_source, meta) or ""
        handle = (meta.get("author") or "") if platform == "bluesky" else None
        article = {"title": _social_title(platform, handle, original), "summary": original}
        english_fields(article)
        if not article.get("original_summary"):
            # The translator judged the original English; the post is its own text.
            article["original_summary"] = None
        if args.dry_run:
            print(f"- {uri}\n    now: {article['summary'][:110]!r}")
        else:
            db.facade._execute_with_rollback(text(
                "UPDATE articles SET title = :t, summary = :s, original_title = :ot, original_summary = :os WHERE uri = :u"
            ), {"t": article["title"], "s": article["summary"], "ot": article.get("original_title"),
                "os": article.get("original_summary"), "u": uri})
        fixed += 1
    print(f"{'would fix' if args.dry_run else 'fixed'} from stored original: {fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
