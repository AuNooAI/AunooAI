#!/usr/bin/env python3
"""Check every reference cited in a customer report: live, dead, or paywalled.

CLI over ``app/services/reference_check.py`` — the same probing the topic
report build runs automatically (results land under ``reference_check`` on
the period sidecar). Use this to re-check by hand, to check an arbitrary
HTML artifact, or to gate a send script.

Verdicts: ok / paywall / blocked (bot check — may open in a real browser) /
redirect (now lands on a homepage) / dead. Details in the module docstring.

References come from one of three places:

    # A rendered HTML report (checks every external link in it)
    .venv/bin/python scripts/check_report_references.py --html report.html

    # The cited corpus of one or more analysis runs, straight from the DB
    .venv/bin/python scripts/check_report_references.py --run-id <horizon_id> [--run-id ...]

    # A plain text file, one URL per line
    .venv/bin/python scripts/check_report_references.py --urls urls.txt

Options: --csv out.csv writes the full result table; --concurrency (default 8)
and --timeout (default 15s) tune the probing; --fail-on-dead exits 1 if any
reference is dead, so the check can gate a send script.

Read-only against the web and the DB. Run from the tenant directory so the
tenant's .env supplies DB credentials for --run-id mode.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from html import unescape
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# load_dotenv() with no path walks up from THIS file's directory, which pins
# the script to its home tenant's .env. The tenant is the directory you run
# from, so prefer the CWD's .env.
_cwd_env = os.path.join(os.getcwd(), ".env")
load_dotenv(_cwd_env if os.path.exists(_cwd_env) else None)

from app.services.reference_check import check_urls, summarize, VERDICT_ORDER

_HREF_RE = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\'#]+)["\']', re.I)


def _urls_from_html(path: str) -> list:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    urls, seen = [], set()
    for m in _HREF_RE.finditer(text):
        u = unescape(m.group(1)).strip()
        if not u.lower().startswith(("http://", "https://")):
            continue
        host = urlsplit(u).netloc.lower()
        # Our own product links (provenance footer etc.) are not references.
        if host.endswith("aunoo.ai"):
            continue
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _urls_from_file(path: str) -> list:
    urls, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            u = line.strip()
            if u.lower().startswith(("http://", "https://")) and u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def _urls_from_runs(run_ids: list) -> list:
    """The numbered corpus each run cited as [1], [2], … — same rows the
    references slide renders (future_horizon_articles join articles)."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    urls, seen = [], set()
    try:
        with conn.cursor() as cur:
            for rid in run_ids:
                cur.execute("""
                    SELECT a.uri FROM future_horizon_articles fha
                    JOIN articles a ON a.uri = fha.article_uri
                    WHERE fha.horizon_id = %s
                    ORDER BY fha.id ASC
                """, (rid,))
                rows = cur.fetchall()
                if not rows:
                    print(f"warning: run {rid} has no cited-corpus rows",
                          file=sys.stderr)
                for (uri,) in rows:
                    u = (uri or "").strip()
                    if u.lower().startswith(("http://", "https://")) and u not in seen:
                        seen.add(u)
                        urls.append(u)
    finally:
        conn.close()
    return urls


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check report references: live, paywalled, or dead.")
    src = ap.add_argument_group("reference sources (give at least one)")
    src.add_argument("--html", action="append", default=[],
                     help="rendered HTML report file")
    src.add_argument("--urls", action="append", default=[],
                     help="text file, one URL per line")
    src.add_argument("--run-id", action="append", default=[],
                     help="analysis run id (horizon_id) — cited corpus from DB")
    ap.add_argument("--csv", help="write full results to this CSV file")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--fail-on-dead", action="store_true",
                    help="exit 1 if any reference is dead")
    args = ap.parse_args()

    urls: list = []
    seen: set = set()
    for path in args.html:
        urls += [u for u in _urls_from_html(path) if not (u in seen or seen.add(u))]
    for path in args.urls:
        urls += [u for u in _urls_from_file(path) if not (u in seen or seen.add(u))]
    if args.run_id:
        urls += [u for u in _urls_from_runs(args.run_id)
                 if not (u in seen or seen.add(u))]
    if not urls:
        ap.error("no URLs found — give --html, --urls, or --run-id")

    print(f"Checking {len(urls)} reference(s), "
          f"concurrency {args.concurrency}, timeout {args.timeout:.0f}s …\n")
    results = asyncio.run(check_urls(urls, concurrency=args.concurrency,
                                     timeout=args.timeout))

    order = {"dead": 0, "redirect": 1, "blocked": 2, "paywall": 3, "ok": 4}
    results.sort(key=lambda r: (order.get(r["verdict"], 9), r["url"]))

    counts = summarize(results)
    for r in results:
        status = r["status"] if r["status"] != "" else "—"
        print(f"[{r['verdict']:>8}] {status:>3}  {r['url']}")
        if r["verdict"] != "ok":
            print(f"           {r['note']}")

    print("\nSummary: " + ", ".join(
        f"{counts.get(k, 0)} {k}" for k in VERDICT_ORDER))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["verdict", "status", "url",
                                               "final_url", "note"])
            w.writeheader()
            w.writerows(results)
        print(f"Full table written to {args.csv}")

    if args.fail_on_dead and counts.get("dead", 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
