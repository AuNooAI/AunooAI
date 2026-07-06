"""Recompose stored Five Signals rows after the subagent-unwrap fix.

The saas validation report nests each subagent block as
``{"status": ..., "output": {...}}``; ``bw_signals_service`` used to read
those blocks flat, so every stored screen had a blinded source row, a
corroboration row stuck at "0 corroborators / no open-web evidence
graded", and a coordination flag that could never fire.

The raw ``validation`` / ``reach`` / ``xnet`` payloads are stored intact
on ``bw_article_signals``, so the composed ``signals`` / ``verdict`` /
``composite_score`` can be rebuilt in place without re-running the saas
jobs. Idempotent; skips rows that hold no payloads at all.

Run from the tenant root:
    .venv/bin/python scripts/recompose_bw_signals.py [--dry-run]
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services.bw_signals_service import _compose_signals  # noqa: E402


def main(dry_run: bool) -> None:
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text(
            "SELECT article_uri, brand_id, status, validation, reach, xnet,"
            "       verdict, composite_score"
            " FROM bw_article_signals WHERE status = 'completed'"
        )).fetchall()

        def _pj(v):
            return v if isinstance(v, dict) or v is None else json.loads(v)

        changed = 0
        for r in rows:
            uri, brand_id, status = r[0], r[1], r[2]
            validation, reach, xnet = _pj(r[3]), _pj(r[4]), _pj(r[5])
            if validation is None and reach is None and xnet is None:
                print(f"skip (no payloads): {uri} brand={brand_id}")
                continue
            signals, verdict, composite = _compose_signals(validation, reach, xnet)
            old_c = float(r[7]) if r[7] is not None else None
            marker = "" if composite == old_c else "  <-- changed"
            print(f"{uri} brand={brand_id}: verdict={verdict} "
                  f"composite {old_c} -> {composite}{marker}")
            if composite != old_c:
                changed += 1
            if not dry_run:
                conn.execute(text(
                    "UPDATE bw_article_signals SET signals = :s, verdict = :v,"
                    " composite_score = :c, updated_at = NOW()"
                    " WHERE article_uri = :u AND brand_id = :b"
                ), {"s": json.dumps(signals), "v": verdict, "c": composite,
                    "u": uri, "b": brand_id})
        if not dry_run:
            conn.commit()
        print(f"\n{len(rows)} completed rows, {changed} composite changes"
              f"{' (dry run — nothing written)' if dry_run else ' — written'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
