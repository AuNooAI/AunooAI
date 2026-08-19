#!/usr/bin/env python3
"""Drain emerging-topic detection, restart the service, and let runs resume.

Replaces "check for in-flight runs, then restart". That sequence always has a
window between the check and the restart in which a run can start, and on
2026-08-19 it cost a paying customer's detection run: the check printed
"1 runs in flight", the restart went ahead in the same command, and the run was
killed mid-flight.

This closes the window with a reader-writer advisory lock instead of a poll.
Every detection run holds MAINTENANCE_KEY *shared* for its whole life. This tool
takes the same key *exclusive*, which PostgreSQL grants only once every shared
holder has let go. So a single blocking acquire does both halves of the job:

  * no new run can start, because a shared lock cannot be taken while an
    exclusive one is held; and
  * the acquire does not return until every in-flight run has finished.

There is no moment where a run can slip through, because the interlock is the
same object the runs themselves take.

Usage:
    python scripts/detection_drain.py --status
    python scripts/detection_drain.py --wait 900
    python scripts/detection_drain.py --wait 900 --restart bugfixing.aunoo.ai.service
"""

import argparse
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402
from app.services.emerging_topics.run_lock import (  # noqa: E402
    MAINTENANCE_KEY,
    _LOCK_NAMESPACE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("detection_drain")


def _connection():
    return get_database_instance()._temp_get_connection()


def active_runs(conn):
    """Runs the database still believes are in flight."""
    return conn.execute(text("""
        SELECT id, topic_filter,
               round(EXTRACT(EPOCH FROM (NOW() - run_date)) / 60) AS age_min
        FROM detection_runs
        WHERE status = 'running'
        ORDER BY run_date
    """)).fetchall()


def interlock_holders(conn):
    """Sessions currently holding the maintenance interlock, and in which mode."""
    return conn.execute(text("""
        SELECT pid, mode, granted
        FROM pg_locks
        WHERE locktype = 'advisory'
          AND classid = :ns
          AND objid = :key
        ORDER BY granted DESC, pid
    """), {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY}).fetchall()


def show_status() -> int:
    conn = _connection()
    try:
        runs = active_runs(conn)
        holders = interlock_holders(conn)
        conn.commit()
    finally:
        conn.close()

    if runs:
        logger.info("%s detection run(s) in flight:", len(runs))
        for run_id, topic_filter, age in runs:
            logger.info("  run %s scope=%s age=%smin", run_id,
                        topic_filter or "<global>", age)
    else:
        logger.info("no detection runs in flight")

    exclusive = [h for h in holders if h[1] == "ExclusiveLock"]
    shared = [h for h in holders if h[1] != "ExclusiveLock"]
    if exclusive:
        logger.warning("a drain currently holds the interlock (pid %s)",
                       exclusive[0][0])
    logger.info("%s session(s) hold the interlock shared", len(shared))
    return 0


# A 'running' row younger than this may still be a live run on a process that
# predates the interlock, so the drain refuses to walk past it.
SUSPICIOUS_AGE_MINUTES = 120


def drain(wait_seconds: int, restart_unit: str = None, force: bool = False) -> int:
    """Block new runs, wait for the active ones, optionally restart."""
    conn = _connection()
    try:
        before = active_runs(conn)
        if before:
            logger.info(
                "waiting for %s in-flight run(s) to finish (up to %ss)",
                len(before), wait_seconds,
            )
            for run_id, topic_filter, age in before:
                logger.info("  run %s scope=%s age=%smin", run_id,
                            topic_filter or "<global>", age)
        else:
            logger.info("no runs in flight; taking the interlock")

        # lock_timeout bounds the wait. The acquire itself is the drain: it
        # returns only when every shared holder has released.
        conn.execute(text("SET lock_timeout = :ms"),
                     {"ms": f"{max(1, wait_seconds) * 1000}"})
        try:
            conn.execute(text("SELECT pg_advisory_lock(:ns, :key)"),
                         {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY})
            conn.commit()
        except Exception as exc:
            conn.rollback()
            still = active_runs(conn)
            conn.commit()
            logger.error(
                "could not drain within %ss: %s", wait_seconds,
                str(exc).splitlines()[0],
            )
            for run_id, topic_filter, age in still:
                logger.error("  still running: run %s scope=%s age=%smin",
                             run_id, topic_filter or "<global>", age)
            logger.error("nothing was restarted; the service is untouched")
            return 1

        logger.info("interlock held: no run is active and none can start")

        remaining = active_runs(conn)
        conn.commit()
        recent = [r for r in remaining if (r[2] or 0) < SUSPICIOUS_AGE_MINUTES]
        stale = [r for r in remaining if (r[2] or 0) >= SUSPICIOUS_AGE_MINUTES]

        if stale:
            # Old enough that no process is plausibly still working on them.
            logger.info(
                "%s row(s) read 'running' but hold no interlock and are older "
                "than %s minutes — abandoned rows, ignoring:",
                len(stale), SUSPICIOUS_AGE_MINUTES,
            )
            for run_id, topic_filter, age in stale:
                logger.info("  run %s scope=%s age=%smin", run_id,
                            topic_filter or "<global>", age)

        if recent and not force:
            # A recent 'running' row holding no interlock is a run started by a
            # process that predates the interlock — a live run the drain cannot
            # see. Assuming it is an orphan is how this tool killed wiley run
            # 514 and wileytest run 2991 on 2026-08-19, during the very deploy
            # that introduced the interlock. Refuse instead of guessing.
            logger.error(
                "%s recent run(s) read 'running' but hold no interlock. Either "
                "they are live runs started before this interlock was deployed, "
                "or they are orphans. This tool cannot tell them apart:",
                len(recent),
            )
            for run_id, topic_filter, age in recent:
                logger.error("  run %s scope=%s age=%smin", run_id,
                             topic_filter or "<global>", age)
            logger.error(
                "Nothing was restarted. Wait for them to finish, or re-run with "
                "--force if you have confirmed they are not live."
            )
            return 1

        if recent and force:
            logger.warning(
                "--force: proceeding past %s recent run(s) that hold no "
                "interlock; any live one will be killed", len(recent),
            )

        if restart_unit:
            logger.info("restarting %s", restart_unit)
            result = subprocess.run(
                ["sudo", "systemctl", "restart", restart_unit],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.error("restart failed: %s", result.stderr.strip())
                logger.error("releasing the interlock; detection resumes")
                return 1
            logger.info("restart complete")

        return 0
    finally:
        # Closing the connection releases the exclusive lock, which is what lets
        # detection resume. Explicit unlock first so the intent is visible.
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"),
                         {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY})
            conn.commit()
            logger.info("interlock released; detection may resume")
        except Exception:
            logger.info("interlock released by closing the connection")
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true",
                        help="report in-flight runs and interlock holders")
    parser.add_argument("--wait", type=int, default=900,
                        help="seconds to wait for in-flight runs (default 900)")
    parser.add_argument("--restart", metavar="UNIT",
                        help="systemd unit to restart once drained")
    parser.add_argument("--force", action="store_true",
                        help="proceed past recent 'running' rows that hold no "
                             "interlock (they may be live runs on older code)")
    args = parser.parse_args()

    if args.status:
        return show_status()
    return drain(args.wait, args.restart, args.force)


if __name__ == "__main__":
    sys.exit(main())
