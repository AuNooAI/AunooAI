#!/usr/bin/env python3
"""Move stored profiles of bots off the person roles.

New profiles get this at build time (social_profile_service.looks_automated);
this applies the same rule to profiles stored before it. Only accounts read
as practitioner or analyst_or_press change, to promoter_or_bot, with the
reason kept in metadata.automated. No platform or model call.

    python scripts/mark_automated_accounts.py            # list what would change
    python scripts/mark_automated_accounts.py --apply    # change it
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the changes")
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services.social_profile_service import _PERSON_ROLES, looks_automated

    conn = get_database_instance()._temp_get_connection()
    rows = conn.execute(text("""
        SELECT id, platform, handle, display_name, bio, metadata->>'market_role'
          FROM social_accounts
         WHERE metadata->>'market_role' = ANY(:roles)
    """), {"roles": list(_PERSON_ROLES)}).fetchall()
    changed = 0
    for acct_id, platform, handle, name, bio, role in rows:
        why = looks_automated(handle, name, bio)
        if not why:
            continue
        changed += 1
        print(f"{platform}/{handle}: {role} -> promoter_or_bot ({why})")
        if args.apply:
            conn.execute(text("""
                UPDATE social_accounts
                   SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:m AS jsonb)
                 WHERE id = :id
            """), {"id": acct_id, "m": json.dumps({"market_role": "promoter_or_bot",
                                                    "automated": why})})
    if args.apply:
        conn.commit()
    print(f"{changed} of {len(rows)} accounts {'changed' if args.apply else 'would change'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
