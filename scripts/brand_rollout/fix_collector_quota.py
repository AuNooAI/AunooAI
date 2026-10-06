#!/usr/bin/env python3
"""Put the older NewsAPI, NewsData and TheNewsAPI collectors on the shared
quota ledger (6 Oct 2026 wileytest review). Copies shared_ledger.py from
canonical and templates/provider_quota_lite.py into the site, then patches
the three collectors at fixed anchors. Every anchor must match or nothing is
written for that file. Idempotent. Backups in /var/tmp/brand_rollout/backup/.

    fix_collector_quota.py <site tree> [...] [--apply]
"""
import os
import shutil
import sys
import time

CANON = "/home/orochford/tenants/bugfixing.aunoo.ai"
HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "# shared-quota"

RATE_RETURN = "        return self.requests_today < self.daily_limit"


def rate_gate(provider):
    return ("        if self.requests_today >= self.daily_limit:\n"
            "            return False\n"
            f"        # The key is shared across sites: ask the host-wide ledger.  {MARK}\n"
            "        from app.services.provider_quota_lite import quota_allows\n"
            f"        return quota_allows(\"{provider}\", self.api_key)")


PATCHES = {
    "newsdata_collector.py": [
        (RATE_RETURN, rate_gate("newsdata"), 1),
        ('logger.error(f"NewsData.io API error {response.status}: {error_message}")',
         'logger.error(f"NewsData.io API error {response.status}: {error_message}")\n'
         '{ind}from app.services.provider_quota_lite import quota_note  ' + MARK + '\n'
         '{ind}quota_note("newsdata", self.api_key, response.status, error_message)', None),
        ('logger.error(f"NewsData.io API error: {response.status}")',
         'logger.error(f"NewsData.io API error: {response.status}")\n'
         '{ind}from app.services.provider_quota_lite import quota_note  ' + MARK + '\n'
         '{ind}quota_note("newsdata", self.api_key, response.status)', None),
    ],
    "thenewsapi_collector.py": [
        (RATE_RETURN, rate_gate("thenewsapi"), 1),
        ('logger.error(f"❌ Error Response (JSON): {error_data}")',
         'logger.error(f"❌ Error Response (JSON): {error_data}")\n'
         '{ind}from app.services.provider_quota_lite import quota_note  ' + MARK + '\n'
         '{ind}quota_note("thenewsapi", self.api_key, response_status, error_data)', None),
        ('logger.error(f"❌ Error Response (Text): {error_text[:500]}...")',
         'logger.error(f"❌ Error Response (Text): {error_text[:500]}...")\n'
         '{ind}from app.services.provider_quota_lite import quota_note  ' + MARK + '\n'
         '{ind}quota_note("thenewsapi", self.api_key, response_status, error_text[:500])', None),
    ],
    "newsapi_collector.py": [
        ("            # Update request counter in the database\n            self._update_request_counter()",
         "            # The key is shared across sites: ask the host-wide ledger.  " + MARK + "\n"
         "            from app.services.provider_quota_lite import quota_allows, quota_note\n"
         "            if not quota_allows(\"newsapi\", self.api_key):\n"
         "                return []\n"
         "            # Update request counter in the database\n            self._update_request_counter()", 1),
        ('logger.error(f"NewsAPI rate limit exceeded: {error_msg}")',
         'logger.error(f"NewsAPI rate limit exceeded: {error_msg}")\n'
         '{ind}quota_note("newsapi", self.api_key, 429, error_msg)  ' + MARK, 1),
    ],
}


def patch_text(src, pairs):
    out = src
    for old, new, expected in pairs:
        n = out.count(old)
        if n == 0 or (expected is not None and n != expected):
            return None, f"anchor found {n} times: {old[:60]!r}"
        lines, res = out.split("\n"), []
        if "\n" in old:
            out = out.replace(old, new)
            continue
        for ln in lines:
            if old in ln:
                ind = ln[: len(ln) - len(ln.lstrip())]
                res.append(ln.replace(old, new.replace("{ind}", ind)))
            else:
                res.append(ln)
        out = "\n".join(res)
    return out, None


def main():
    apply = "--apply" in sys.argv
    bad = 0
    for tree in [a for a in sys.argv[1:] if not a.startswith("--")]:
        site = os.path.basename(tree.rstrip("/"))
        plans = []
        for fname, pairs in PATCHES.items():
            p = os.path.join(tree, "app", "collectors", fname)
            src = open(p, encoding="utf-8").read()
            if MARK in src:
                print(f"{site}/{fname}: already patched")
                continue
            new, err = patch_text(src, pairs)
            if err:
                print(f"{site}/{fname}: {err}; nothing written")
                bad += 1
                continue
            compile(new, p, "exec")
            plans.append((p, new))
        if apply:
            for mod, src in (("shared_ledger.py", os.path.join(CANON, "app/services/shared_ledger.py")),
                             ("provider_quota_lite.py", os.path.join(HERE, "templates/provider_quota_lite.py"))):
                dst = os.path.join(tree, "app", "services", mod)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
            for p, new in plans:
                shutil.copy2(p, f"/var/tmp/brand_rollout/backup/{site}-{os.path.basename(p)}.quota.{time.strftime('%H%M%S')}")
                open(p, "w", encoding="utf-8").write(new)
        print(f"{site}: {'patched' if apply else 'would patch'} {len(plans)} collector(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
