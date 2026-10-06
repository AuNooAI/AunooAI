#!/usr/bin/env python3
"""Keep links to social posts out of RSS news (6 Oct 2026 wileytest review:
a Bluesky post from a newsletter feed was stored as an article with no social
metadata). Inserts a host check right after RssFeedMonitor._store_article
reads the URL. Idempotent; refuses unless the anchor matches once.

    fix_rss_social_links.py <site tree> [...] [--apply]
"""
import os, shutil, sys, time
MARK = "# rss: social-post links are not news"
ANCHOR = """        url = article.get('url', '').strip()
        if not url:
            return False
"""
INSERT = ANCHOR + """        {mark}
        from urllib.parse import urlparse as _urlparse
        _host = (_urlparse(url).hostname or '').lower()
        _social = ('bsky.app', 'x.com', 'twitter.com', 'reddit.com', 'truthsocial.com', 'instagram.com',
                   'tiktok.com', 'facebook.com', 'threads.net', 'mastodon.social')
        if any(_host == h or _host.endswith('.' + h) for h in _social):
            logger.info(f"RSS item skipped: {{url[:120]}} is a social post, not news")
            return False
""".replace("{mark}", MARK)
# The newer monitor (canonical, abm, bwtemplate) returns a status string; a
# skipped social link is finished work, so it returns STORE_EXISTING, which is
# never queued for retry.
ANCHOR2 = """        url = (article.get('url') or '').strip()
        if not url:
            self._last_store_error = "entry has no URL"
            return STORE_FAILED
"""
INSERT2 = INSERT.replace(ANCHOR, ANCHOR2).replace("            return False\n", "            return STORE_EXISTING\n")
apply = "--apply" in sys.argv; bad = 0
for tree in [a for a in sys.argv[1:] if not a.startswith("--")]:
    site = os.path.basename(tree.rstrip("/")); p = os.path.join(tree, "app/tasks/rss_feed_monitor.py")
    if not os.path.exists(p): continue
    s = open(p, encoding="utf-8").read()
    if MARK in s: print(f"{site}: already patched"); continue
    if s.count(ANCHOR) == 1:
        new = s.replace(ANCHOR, INSERT.replace("{{", "{").replace("}}", "}"))
    elif s.count(ANCHOR2) == 1:
        new = s.replace(ANCHOR2, INSERT2.replace("{{", "{").replace("}}", "}"))
    else:
        print(f"{site}: no anchor matched once; nothing written"); bad += 1; continue
    compile(new, p, "exec")
    if apply:
        shutil.copy2(p, f"/var/tmp/brand_rollout/backup/{site}-rss_feed_monitor.py.{time.strftime('%H%M%S')}")
        open(p, "w", encoding="utf-8").write(new)
    print(f"{site}: {'patched' if apply else 'would patch'}")
sys.exit(1 if bad else 0)
