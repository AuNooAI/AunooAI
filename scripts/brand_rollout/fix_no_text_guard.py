#!/usr/bin/env python3
"""Let the ingest no-text guard use the scraped page before giving up.

The guard ("Step 0b: NO-TEXT GUARD" in automated_ingest_service.py) marks an
article enrichment_failed when the collector gave no summary or content. But
batch runs pre-scrape every article (article['_scraped_content']) and save the
page to raw_articles, and the guard never looked there: on wileytest 349
articles a week failed this way although 540 of 552 recent failures had a
scraped page of more than 200 characters (6 Oct 2026 data quality review).

This inserts, just before the guard, a fallback that uses the scraped page
(the article's own, else raw_articles) as the article's content when it has
at least 200 characters. The analysis reads summary or content, so it then
writes a real summary from the page. `content` is not a stored column.

    fix_no_text_guard.py <site tree> [...] [--apply]
"""
import os
import re
import shutil
import sys
import time

MARK = "# no-text-guard: scraped page fallback"
BLOCK = """{i}{mark}
{i}# A scraped page counts as text (6 Oct 2026): use it before giving up.
{i}if article.get('title') and not (article.get('summary') or article.get('content')):
{i}    _page = (article.get('_scraped_content') or '').strip()
{i}    if not _page:
{i}        try:
{i}            _raw = await self.async_db.get_raw_article_async(article_uri)
{i}            _page = ((_raw or {{}}).get('raw_markdown') or '').strip()
{i}        except Exception:
{i}            _page = ''
{i}    if len(_page) >= 200:
{i}        article['content'] = _page[:20000]
{i}        self.logger.info(f"📄 Article {{article_uri}}: no summary, using the scraped page ({{len(_page)}} chars)")
"""
GUARD = re.compile(r"^(\s+)if .*not \(article\.get\('summary'\) or article\.get\('content'\)\).*$", re.M)


def main() -> int:
    apply = "--apply" in sys.argv
    bad = 0
    for tree in [a for a in sys.argv[1:] if not a.startswith("--")]:
        site = os.path.basename(tree.rstrip("/"))
        p = os.path.join(tree, "app", "services", "automated_ingest_service.py")
        if not os.path.exists(p):
            continue
        s = open(p, encoding="utf-8").read()
        if MARK in s:
            print(f"{site}: already has the fallback")
            continue
        start = s.find("NO-TEXT GUARD")
        if start < 0:
            print(f"{site}: no NO-TEXT GUARD here; nothing to do")
            continue
        m = GUARD.search(s, start)
        if not m or "get_raw_article_async" not in open(os.path.join(tree, "app", "services", "async_db.py"), encoding="utf-8").read():
            print(f"{site}: guard line or raw-article reader not found; left alone")
            bad += 1
            continue
        new = s[:m.start()] + BLOCK.format(i=m.group(1), mark=MARK) + s[m.start():]
        try:
            compile(new, p, "exec")
        except SyntaxError as e:
            print(f"{site}: result does not compile ({e}); left alone")
            bad += 1
            continue
        if apply:
            shutil.copy2(p, f"/var/tmp/brand_rollout/backup/{site}-automated_ingest_service.py.notext.{time.strftime('%H%M%S')}")
            open(p, "w", encoding="utf-8").write(new)
        print(f"{site}: {'fixed' if apply else 'would fix'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
