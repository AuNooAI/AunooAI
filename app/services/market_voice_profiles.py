"""Profile the outside accounts posting about a market.

Top Voices ranks handles. A handle on its own is a stranger: the account with
the most reactions on one market turned out to be a founder promoting their
own tools, with no part in the market at all, and the table could not say so.
Brand monitoring already builds account profiles (bio, reach, what they post
about, an LLM summary) through ``social_profile_service``. This runs that same
build for a market's voices, so the two features share one ``social_accounts``
row per handle.

Profiles are built on request, never on a schedule: each one is two xpoz
calls and one short model call. ``profile_many`` runs as a background task
because fifty accounts take several minutes, and reports progress through
``status``.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# One job per market at a time. Progress lives here because a bulk profile
# is a few minutes of work and the page polls for it.
_JOBS: Dict[int, Dict[str, Any]] = {}

PROFILABLE = {"twitter", "bluesky", "reddit", "instagram", "tiktok"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status(market_id: int) -> Dict[str, Any]:
    job = _JOBS.get(market_id)
    if not job:
        return {"state": "idle", "market_id": market_id}
    return {k: v for k, v in job.items() if k != "task"}


def running(market_id: int) -> bool:
    job = _JOBS.get(market_id)
    return bool(job and job.get("state") == "running")


async def profile_one(db, platform: str, handle: str, market_name: str) -> Optional[Dict[str, Any]]:
    """Build (or rebuild) one account's profile, framed by the market."""
    from app.services.social_profile_service import SocialProfileService
    platform = (platform or "").lower()
    if platform not in PROFILABLE:
        raise ValueError(f"Accounts on {platform or 'this platform'} cannot be profiled")
    svc = SocialProfileService()
    return await svc.build_profile(db, platform, handle, brand=None, context=market_name)


# xpoz rate-limits per key, and the key is shared across tenants. Three
# builds at once got 28 of 50 accounts refused with 429 on the first run, so
# the job is sequential, pauses between accounts, and backs off on a 429.
PACE_SECONDS = 2.0
RETRY_WAITS = (10, 30, 60)


def _root_message(exc: BaseException) -> str:
    """The message under anyio's ExceptionGroup wrapper, which is what the
    xpoz client raises and which says only "unhandled errors in a TaskGroup"."""
    seen = 0
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and seen < 5:
        exc = exc.exceptions[0]
        seen += 1
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def _rate_limited(message: str) -> bool:
    return "429" in message or "Too Many Requests" in message


async def _build_with_retry(db, platform: str, handle: str, market_name: str):
    """One profile, retried on a rate limit; anything else raises with the
    underlying message rather than the TaskGroup wrapper."""
    for attempt, wait in enumerate(RETRY_WAITS + (None,)):
        try:
            return await profile_one(db, platform, handle, market_name)
        except Exception as exc:  # noqa: BLE001 — unwrap, decide, re-raise
            message = _root_message(exc)
            if _rate_limited(message) and wait is not None:
                logger.info("xpoz rate limit on %s/%s, waiting %ss (attempt %d)",
                            platform, handle, wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise RuntimeError(message) from exc
    return None


def start_many(db, market_id: int, market_name: str, voices: List[Dict[str, Any]],
               *, refresh: bool = False, concurrency: int = 1) -> Dict[str, Any]:
    """Queue profiles for every voice that lacks one (or all, with refresh).

    Returns the job status straight away. Raises RuntimeError if a job for the
    market is still running.
    """
    if running(market_id):
        raise RuntimeError("A profiling run for this market is already in progress")
    todo = []
    skipped = 0
    for v in voices:
        platform = (v.get("platform") or "").lower()
        account = v.get("account") or {}
        if platform not in PROFILABLE:
            skipped += 1
            continue
        if account.get("profiled") and not refresh:
            skipped += 1
            continue
        todo.append((platform, v.get("author")))
    job: Dict[str, Any] = {
        "state": "running" if todo else "done",
        "market_id": market_id,
        "total": len(todo), "done": 0, "built": 0, "failed": 0,
        "skipped": skipped, "errors": [],
        "started_at": _now(), "finished_at": None if todo else _now(),
    }
    _JOBS[market_id] = job
    if todo:
        job["task"] = asyncio.create_task(
            _run(db, job, market_name, todo, concurrency))
    return status(market_id)


async def _run(db, job: Dict[str, Any], market_name: str,
               todo: List[tuple], concurrency: int) -> None:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(platform: str, handle: str) -> None:
        async with sem:
            try:
                prof = await _build_with_retry(db, platform, handle, market_name)
                if prof:
                    job["built"] += 1
                else:
                    job["failed"] += 1
                    job["errors"].append(f"@{handle} ({platform}): no such account")
            except Exception as exc:  # noqa: BLE001 — one bad handle must not end the run
                job["failed"] += 1
                job["errors"].append(f"@{handle} ({platform}): {exc}")
                logger.warning("voice profile %s/%s failed: %s", platform, handle, exc)
            finally:
                job["done"] += 1
                await asyncio.sleep(PACE_SECONDS)

    try:
        await asyncio.gather(*(one(p, h) for p, h in todo))
    finally:
        job["state"] = "done"
        job["finished_at"] = _now()
        job["errors"] = job["errors"][:20]
