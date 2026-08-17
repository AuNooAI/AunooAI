"""Event-loop health monitor.

Measures the gap between when ``asyncio.sleep(1)`` *should* wake up and when
it actually does. A healthy loop wakes within milliseconds; when sync
blocking work hijacks the loop the gap grows into seconds — exactly the
signature of the wileytest hangs we've been chasing.

Two surfaces:

- A background task that samples lag every 5s and logs a WARNING when it
  crosses a threshold (default 1s). Recent samples are kept in a ring
  buffer so the admin endpoint can show recent loop health.

- ``GET /api/admin/event-loop-status`` returns recent lag samples and
  optionally dumps every Python thread's stack trace (set ``?dump=1``).
  Useful next time the service stops responding — hit it and read the
  diagnosis instead of guessing.
"""
from __future__ import annotations

import asyncio
import faulthandler
import io
import logging
import os
import sys
import tempfile
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Tunables
SAMPLE_INTERVAL_SEC = float(os.getenv("EVENT_LOOP_SAMPLE_INTERVAL", "5.0"))
WARN_THRESHOLD_SEC = float(os.getenv("EVENT_LOOP_WARN_THRESHOLD", "1.0"))
RING_BUFFER_SIZE = int(os.getenv("EVENT_LOOP_RING_BUFFER", "120"))  # ~10 min @ 5s
# Watchdog: if the loop hasn't cycled within this many seconds, faulthandler
# dumps every thread's stack. Must be > SAMPLE_INTERVAL_SEC + scheduling jitter.
WATCHDOG_TIMEOUT_SEC = float(os.getenv("EVENT_LOOP_WATCHDOG_TIMEOUT", "8.0"))
# The C-level faulthandler.dump_traceback_later watchdog walks EVERY thread's
# PyThreadState from a timer thread. On a busy server that races thread
# teardown / native-extension execution and SEGVs inside _Py_DumpTracebackThreads
# (observed on wileytest, 2026-07-30). Disabled by default — the async lag
# WARNING below and the admin endpoint's Python-level dump_all_thread_stacks()
# (GIL-safe) cover diagnosis without the crash. Set EVENT_LOOP_WATCHDOG=1 to
# re-enable the C-level dump when actively debugging a hard hang.
WATCHDOG_ENABLED = os.getenv("EVENT_LOOP_WATCHDOG", "0") == "1"

_samples: deque = deque(maxlen=RING_BUFFER_SIZE)


_last_blocking_dump: Optional[str] = None


async def run_event_loop_monitor():
    """Background task — log when the loop scheduling lag is anomalous.

    Uses a parallel watchdog thread that arms ``faulthandler.dump_traceback_later``
    on each iteration. If the event loop fails to cancel within the watchdog
    timeout (because it's blocked), faulthandler dumps every thread's stack
    to a known buffer — capturing the blocker *while it's still running*,
    not after the fact.
    """
    logger.info(
        "Event-loop monitor started (interval=%.1fs, warn>%.2fs, watchdog=%.1fs)",
        SAMPLE_INTERVAL_SEC, WARN_THRESHOLD_SEC, WATCHDOG_TIMEOUT_SEC,
    )
    dump_fd = None
    dump_path = None
    if WATCHDOG_ENABLED:
        try:
            faulthandler.register(10)  # SIGUSR1 → dump all threads to stderr
        except Exception:
            pass
        # Open a tempfile that the C-level faulthandler can write to mid-block.
        dump_fd, dump_path = tempfile.mkstemp(prefix="aunoo_loop_block_", suffix=".log")
        logger.info("Watchdog dumps will land at %s", dump_path)
    else:
        logger.info("C-level faulthandler watchdog disabled (SEGV-prone); "
                    "set EVENT_LOOP_WATCHDOG=1 to enable when debugging a hang")

    while True:
        # Arm the watchdog: if we don't cancel within WATCHDOG_TIMEOUT_SEC, the
        # C-level faulthandler will dump stacks. This works *while the loop is
        # blocked* because faulthandler runs from a separate timer thread.
        if WATCHDOG_ENABLED:
            faulthandler.dump_traceback_later(
                WATCHDOG_TIMEOUT_SEC, repeat=False, file=dump_fd,
            )

        scheduled_at = time.monotonic()
        await asyncio.sleep(SAMPLE_INTERVAL_SEC)
        actual_at = time.monotonic()
        lag = actual_at - scheduled_at - SAMPLE_INTERVAL_SEC

        # Cancel the watchdog now that we made it through the sleep.
        if WATCHDOG_ENABLED:
            faulthandler.cancel_dump_traceback_later()

        sample = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lag_seconds": round(lag, 3),
            "thread_count": threading.active_count(),
        }
        _samples.append(sample)
        if lag > WARN_THRESHOLD_SEC:
            logger.warning(
                "⚠️  Event loop lag %.2fs (threads=%d) — something is blocking the loop",
                lag, sample["thread_count"],
            )
            # If the C-level watchdog is enabled and fired during this lag,
            # capture the dump so the admin endpoint can serve it.
            if WATCHDOG_ENABLED and dump_path:
                global _last_blocking_dump
                try:
                    with open(dump_path, "r") as f:
                        contents = f.read()
                    if contents.strip():
                        _last_blocking_dump = (
                            f"=== Watchdog stack capture at {sample['ts']} "
                            f"(loop lag {lag:.2f}s) ===\n{contents}"
                        )
                        # Truncate the file for next iteration.
                        with open(dump_path, "w") as f:
                            f.write("")
                except Exception as e:
                    logger.debug("Failed to read watchdog dump: %s", e)


def get_last_blocking_dump() -> Optional[str]:
    """Return the most recent stack dump captured during a long loop lag."""
    return _last_blocking_dump


def get_recent_samples(limit: int = 60) -> list:
    return list(_samples)[-limit:]


def dump_all_thread_stacks() -> str:
    """Capture stack traces from every Python thread. Use when the loop is
    sluggish — the stack trace tells you which thread is holding work."""
    out = io.StringIO()
    out.write(f"=== Thread dump at {datetime.now(timezone.utc).isoformat()} ===\n")
    out.write(f"Active Python thread count: {threading.active_count()}\n\n")
    frames = sys._current_frames()
    for thread in threading.enumerate():
        out.write(f"--- Thread {thread.name} (id={thread.ident}, "
                  f"daemon={thread.daemon}) ---\n")
        frame = frames.get(thread.ident)
        if frame is None:
            out.write("  (no current frame)\n\n")
            continue
        out.write("".join(traceback.format_stack(frame)))
        out.write("\n")
    return out.getvalue()
