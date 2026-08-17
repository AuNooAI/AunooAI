#!/usr/bin/env python
"""Run timeline daily extraction for a specific day, all scopes, with LLM.

The scheduler and the /timeline/generate endpoint both stop at yesterday, so
TODAY's ingestion day is unreachable through normal paths — a problem on a
freshly provisioned tenant whose whole corpus arrived today. Dedup hashes make
re-extraction of the same day safe, so the scheduled pass can still re-cover
the day later (delete the day's timeline_runs rows afterwards to let it).

Usage (from the tenant root, with its venv and .env available):
    .venv/bin/python scripts/force_timeline_day.py [YYYY-MM-DD]

Defaults to today.
"""
import sys

from dotenv import load_dotenv

load_dotenv()  # reads the tenant's .env from the cwd; values held in memory
print("ENV-LOADED", flush=True)

sys.path.insert(0, ".")

from datetime import date

from app.database import Database
from app.services.timeline_events import extract_daily_events, get_timeline_scopes
from app.services.timeline_rollup import refresh_state_doc

target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()

db = Database()
conn = db._temp_get_connection()
try:
    for s in get_timeline_scopes(conn):
        res = extract_daily_events(conn, s["scope_type"], s["scope_id"], target, use_llm=True)
        print(f"{s['scope_type']}:{s['scope_id']} -> {res}", flush=True)
        try:
            refresh_state_doc(conn, s["scope_type"], s["scope_id"])
        except Exception as e:  # noqa: BLE001
            print(f"state-doc refresh failed for {s['scope_id']}: {e}", flush=True)
finally:
    conn.close()
print("DONE", flush=True)
