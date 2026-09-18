#!/usr/bin/env python3
"""Add, list and retire featured items on a market front page.

A featured item is a hand-picked link the page promotes under the lead
story and, on desktop, at the top of the sidebar (table ``market_featured``,
read by ``app/services/market_featured.py``). Rows are never deleted here;
``retire`` switches one off and keeps the record.

    python scripts/market_featured.py list --market 2
    python scripts/market_featured.py add --market 2 --kind whitepaper \\
        --title "The Decoupled SIEM: An Architectural Foundation for Agentic SecOps" \\
        --url https://pages.anvilogic.com/whitepaper-an-architectural-foundation-for-agentic-secops \\
        --publisher Anvilogic --vendor Anvilogic \\
        --byline "Oliver Rochford, Cyberfuturists" \\
        --blurb "..." [--placement both|lead|side] [--ends 2026-10-31]
    python scripts/market_featured.py retire --id 1

The page is rebuilt on the next request; the aisocnews.com nginx micro-cache
keeps the old page for up to 90 seconds.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services import market_featured as mfe  # noqa: E402


def _stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_list(conn, args) -> int:
    rows = conn.execute(text("""
        SELECT id, kind, title, url, publisher, placement, active, sort_order,
               starts_at, ends_at
          FROM market_featured WHERE market_id = :m ORDER BY sort_order, id
    """), {"m": args.market}).mappings().all()
    if not rows:
        print(f"market {args.market}: no featured items")
        return 0
    live = {r["id"] for r in mfe.active(conn, args.market, limit=100)}
    for r in rows:
        state = "LIVE" if r["id"] in live else ("off" if not r["active"] else "outside window")
        print(f'#{r["id"]:<4} {state:<15} {r["placement"]:<5} {r["kind"]:<11} {r["title"]}')
        print(f'      {r["url"]}')
        if r["ends_at"]:
            print(f'      until {r["ends_at"]:%Y-%m-%d}')
    return 0


def cmd_add(conn, args) -> int:
    if args.placement not in mfe.PLACEMENTS:
        print(f"placement must be one of {mfe.PLACEMENTS}", file=sys.stderr)
        return 2
    row = conn.execute(text("""
        INSERT INTO market_featured
               (market_id, kind, title, blurb, url, publisher, byline, vendor,
                placement, sort_order, starts_at, ends_at)
        VALUES (:m, :kind, :title, :blurb, :url, :publisher, :byline, :vendor,
                :placement, :sort_order, :starts_at, :ends_at)
        RETURNING id
    """), {
        "m": args.market, "kind": args.kind, "title": args.title, "blurb": args.blurb,
        "url": args.url, "publisher": args.publisher, "byline": args.byline,
        "vendor": args.vendor or args.publisher, "placement": args.placement,
        "sort_order": args.sort, "starts_at": _stamp(args.starts), "ends_at": _stamp(args.ends),
    }).scalar_one()
    conn.commit()
    print(f"added #{row}: {args.title}")
    return 0


def cmd_retire(conn, args) -> int:
    n = conn.execute(text("UPDATE market_featured SET active = false WHERE id = :id"),
                     {"id": args.id}).rowcount
    conn.commit()
    print(f"retired #{args.id}" if n else f"no row #{args.id}")
    return 0 if n else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--market", type=int, required=True)
    p = sub.add_parser("add")
    p.add_argument("--market", type=int, required=True)
    p.add_argument("--kind", default="whitepaper", help=", ".join(mfe.KIND_LABEL))
    p.add_argument("--title", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--blurb", default=None)
    p.add_argument("--publisher", default=None)
    p.add_argument("--byline", default=None)
    p.add_argument("--vendor", default=None, help="vendor name whose logo mark to show (defaults to publisher)")
    p.add_argument("--placement", default="both", choices=mfe.PLACEMENTS)
    p.add_argument("--sort", type=int, default=0)
    p.add_argument("--starts", default=None, help="ISO date/time; default: now")
    p.add_argument("--ends", default=None, help="ISO date/time; default: open-ended")
    p = sub.add_parser("retire"); p.add_argument("--id", type=int, required=True)
    args = ap.parse_args()
    conn = get_database_instance()._temp_get_connection()
    try:
        return {"list": cmd_list, "add": cmd_add, "retire": cmd_retire}[args.cmd](conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
