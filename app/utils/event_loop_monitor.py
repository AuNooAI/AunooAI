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

_samples: deque = deque(maxlen=RING_BUFFER_SIZE)


async def run_event_loop_monitor():
    """Background task — log when the loop scheduling lag is anomalous."""
    logger.info(
        "Event-loop monitor started (interval=%.1fs, warn>%.2fs)",
        SAMPLE_INTERVAL_SEC, WARN_THRESHOLD_SEC,
    )
    # Enable faulthandler so SIGUSR1 prints all thread stacks — useful
    # complement to the /admin endpoint when nginx returns 502 and the
    # process is mostly unresponsive.
    try:
        faulthandler.register(10)  # signal.SIGUSR1 = 10 on Linux
    except Exception:
        pass

    while True:
        scheduled_at = time.monotonic()
        await asyncio.sleep(SAMPLE_INTERVAL_SEC)
        actual_at = time.monotonic()
        lag = actual_at - scheduled_at - SAMPLE_INTERVAL_SEC
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
