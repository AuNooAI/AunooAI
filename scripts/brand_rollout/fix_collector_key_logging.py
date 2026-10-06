#!/usr/bin/env python3
"""Stop collectors writing API keys into the service journal.

Found by the 6 Oct 2026 wileytest data quality review: NewsData logged its
request params (with `apikey`) at INFO on every request, TheNewsAPI logged
the full request URL (with `api_token=`) and its params on errors, and
NewsAPI logged params (with `apiKey`) at DEBUG. This rewrites those six log
lines to leave the key out; everything else in the line is kept.

    fix_collector_key_logging.py <site tree> [<site tree> ...] [--apply]

Each line is replaced only where the file also builds `params` as a dict
literal, so the dict comprehension is valid. Files are backed up to
/var/tmp/brand_rollout/backup/ before writing. Idempotent.
"""
import os
import shutil
import sys
import time

FIXES = {
    "thenewsapi_collector.py": [
        ('logger.debug(f"TheNewsAPI search params: {params}")',
         'logger.debug(f"TheNewsAPI search params: { {k: v for k, v in params.items() if k != \'api_token\'} }")'),
        ('logger.error(f"❌ Params: {params}")',
         'logger.error(f"❌ Params: { {k: v for k, v in params.items() if k != \'api_token\'} }")'),
        ('logger.error(f"❌ URL: {response.url}")',
         'logger.error(f"❌ URL: {str(response.url).split(\'?\')[0]} (query withheld: it carries the API token)")'),
    ],
    "newsdata_collector.py": [
        ('logger.info(f"NewsData.io API request - URL: {self.base_url}, Params: {params}")',
         'logger.info(f"NewsData.io API request - URL: {self.base_url}, Params: { {k: v for k, v in params.items() if k != \'apikey\'} }")'),
        ('logger.info(f"NewsData.io connection test - URL: {self.base_url}, Params: {params}")',
         'logger.info(f"NewsData.io connection test - URL: {self.base_url}, Params: { {k: v for k, v in params.items() if k != \'apikey\'} }")'),
    ],
    "newsapi_collector.py": [
        ('logger.debug(f"Making NewsAPI request with params: {params}")',
         'logger.debug(f"Making NewsAPI request with params: { {k: v for k, v in params.items() if k != \'apiKey\'} }")'),
    ],
}


def main() -> int:
    apply = "--apply" in sys.argv
    trees = [a for a in sys.argv[1:] if not a.startswith("--")]
    bad = 0
    for tree in trees:
        site = os.path.basename(tree.rstrip("/"))
        for fname, pairs in FIXES.items():
            p = os.path.join(tree, "app", "collectors", fname)
            if not os.path.exists(p):
                continue
            src = open(p, encoding="utf-8").read()
            new, done = src, []
            for old, rep in pairs:
                n = new.count(old)
                if n == 0:
                    continue
                if "params = {" not in new:
                    print(f"{site}/{fname}: params is not a dict literal here; left alone")
                    bad += 1
                    break
                new = new.replace(old, rep)
                done.append(f"{n}x {old[:40]}")
            if new == src:
                continue
            try:
                compile(new, p, "exec")
            except SyntaxError as e:
                print(f"{site}/{fname}: result does not compile ({e}); left alone")
                bad += 1
                continue
            if apply:
                shutil.copy2(p, f"/var/tmp/brand_rollout/backup/{site}-{fname}.{time.strftime('%H%M%S')}")
                open(p, "w", encoding="utf-8").write(new)
            print(f"{site}/{fname}: {'fixed' if apply else 'would fix'} {'; '.join(done)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
