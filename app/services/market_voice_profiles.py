"""Profile the outside accounts posting about a market.

Top Voices ranks handles. A handle on its own is a stranger: the account with
the most reactions on one market turned out to be a founder promoting their
own tools, with no part in the market at all, and the table could not say so.
Brand monitoring already builds account profiles (bio, reach, what they post
about, an LLM summary) through ``social_profile_service``. This runs that same
build for a market's voices, so the two features share one ``social_accounts``
row per handle.

Each profile is two xpoz calls and one short model call. They are built on
request, and since 25 Sep 2026 also by the market scheduler, which profiles a
capped number of the busiest unprofiled voices each day
(``market_monitor._profile_voices``). ``start_many`` runs as a background task
because fifty accounts take several minutes, and reports progress through
``status``.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# One job per market at a time. Progress lives here because a bulk profile
# is a few minutes of work and the page polls for it.
_JOBS: Dict[Any, Dict[str, Any]] = {}

PROFILABLE = {"twitter", "bluesky", "reddit", "instagram", "tiktok"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status(market_id: Any) -> Dict[str, Any]:
    """``market_id`` is the job key: a market id, or "brand:<id>" for a run
    started from a brand's Voices view."""
    job = _JOBS.get(market_id)
    if not job:
        return {"state": "idle", "market_id": market_id}
    return {k: v for k, v in job.items() if k != "task"}


def running(market_id: Any) -> bool:
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


async def reread_one(db, platform: str, handle: str, market_name: str) -> Optional[Dict[str, Any]]:
    """Re-run the model step over a stored profile, no platform call."""
    from app.services.social_profile_service import SocialProfileService
    return await SocialProfileService().reread(db, platform.lower(), handle, market_name)


def link_vendor_accounts(db, market_id: int, days: Optional[int] = None) -> Dict[str, Any]:
    """Record each tagged vendor account on that vendor's profile.

    A voice read as a vendor's own account (not staff), whose organisation is
    a vendor we track on this market, becomes a ``social_account`` identifier
    on that vendor: ``twitter:sentinelone`` with the profile URL as its
    display value. Insert-unless-exists, so re-running adds nothing twice; a
    handle already live on another vendor is left alone.
    """
    from app.services import market_analysis as man
    from app.services.market_import import _upsert_identifier
    conn = db._temp_get_connection()
    market_name = conn.execute(text("SELECT name FROM bw_markets WHERE id = :m"),
                               {"m": market_id}).scalar() or f"market {market_id}"
    voices = man.top_voices(conn, market_id, days=days, limit=200)
    added = 0
    queued: List[Dict[str, Any]] = []
    for v in voices.get("voices") or []:
        tag = v.get("vendor_tag") or {}
        if tag.get("label") != "vendor":
            continue
        acct = v.get("account") or {}
        if not tag.get("brand_id"):
            # A vendor we do not track: nothing to attach the account to, so
            # it goes into the queue a reader fills through "Is your company
            # missing?", for the same person to look at.
            row = _queue_untracked(conn, market_id, v, tag)
            if row:
                queued.append(row)
            continue
        if tag.get("linked"):
            continue
        _upsert_identifier(
            conn, brand_id=int(tag["brand_id"]), kind=man.SOCIAL_IDENTIFIER_KIND,
            normalized=man.social_identifier(v.get("platform"), v.get("author")),
            display=v.get("profile_url") or f"@{v.get('author')}",
            external_id=str(acct["account_id"]) if acct.get("account_id") else None,
            provenance={"source": "top_voices", "how": tag.get("source"),
                        "market_id": market_id, "at": _now()})
        added += 1
    try:
        conn.commit()
    except Exception:  # noqa: BLE001
        pass
    if queued:
        _notify_queued(market_id, market_name, queued)
    return {"linked": added, "queued": len(queued)}


QUEUE_SOURCE = "top_voices"


def _queue_untracked(conn, market_id: int, v: Dict[str, Any],
                     tag: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One vendor-request row per untracked vendor per market, from the
    account's own posting. Skips accounts the profile read as unconnected to
    the market — a vendor of something else is not a missing vendor."""
    org = (tag.get("org") or "").strip()
    acct = v.get("account") or {}
    relation = (acct.get("relation") or "").strip().lower()
    if not org or relation.startswith("no clear connection"):
        return None
    note = (f"Seen on {v.get('platform')} as @{v.get('author')}: {v.get('posts')} post(s) "
            f"about the market, {v.get('engagement')} reactions. "
            + (acct.get("summary") or ""))[:2000]
    row_id = conn.execute(text("""
        INSERT INTO market_vendor_requests
            (market_id, company, website, email, note, source)
        SELECT :m, :c, :w, NULL, :n, :s
        WHERE NOT EXISTS (
            SELECT 1 FROM market_vendor_requests
             WHERE market_id = :m AND lower(company) = lower(:c))
        RETURNING id
    """), {"m": market_id, "c": org[:200], "w": (v.get("profile_url") or "")[:300] or None,
           "n": note, "s": QUEUE_SOURCE}).scalar()
    if not row_id:
        return None
    return {"id": int(row_id), "company": org, "website": v.get("profile_url"),
            "handle": f"@{v.get('author')} ({v.get('platform')})"}


def _notify_queued(market_id: int, market_name: str, rows: List[Dict[str, Any]]) -> None:
    """One mail per run listing the companies queued, to the same address the
    form notifies. Stored first; mail is a convenience."""
    import html as _html
    import os
    to = [a.strip() for a in (os.getenv("MARKET_TRIAL_NOTIFY_EMAIL") or "").split(",")
          if a.strip()]
    if not to:
        logger.info("%d vendor(s) queued from top voices; MARKET_TRIAL_NOTIFY_EMAIL unset, "
                    "no mail sent", len(rows))
        return
    try:
        from app.services.email_service import EmailService
        svc = EmailService()
        if not svc.is_available():
            return
        lines = [f"{r['company']} — {r['handle']} — {r['website'] or '-'} (request {r['id']})"
                 for r in rows]
        text_body = (f"Vendors posting about {market_name} that we do not track:\n"
                     + "\n".join(lines))
        html_body = ("<p>Vendors posting about " + _html.escape(market_name)
                     + " that we do not track:</p><ul>"
                     + "".join(f"<li>{_html.escape(l)}</li>" for l in lines) + "</ul>")
        if svc.send_email(to, f"Untracked vendors seen in Top voices — {market_name}",
                          html_body, text_body):
            conn_ids = [r["id"] for r in rows]
            from app.database import get_database_instance
            conn = get_database_instance()._temp_get_connection()
            conn.execute(text("UPDATE market_vendor_requests SET notified = true "
                              "WHERE id = ANY(:ids)"), {"ids": conn_ids})
            try:
                conn.commit()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001 — never fail the run over mail
        logger.warning("queued-vendor notification failed: %s", exc)


def start_many(db, market_id: int, market_name: str, voices: List[Dict[str, Any]],
               *, refresh: bool = False, mode: str = "build",
               concurrency: int = 1) -> Dict[str, Any]:
    """Queue profiles for every voice that lacks one (or all, with refresh).

    ``mode="reread"`` re-runs the model step over profiles already stored
    (bio and sample posts), for adding the market role without paying for
    the platform fetch again; it skips accounts with no profile.

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
        if mode == "reread":
            if not account.get("profiled") or (account.get("role") and not refresh):
                skipped += 1
                continue
        elif account.get("profiled") and not refresh:
            skipped += 1
            continue
        todo.append((platform, v.get("author")))
    return start_handles(db, market_id, market_name, todo, skipped=skipped,
                         mode=mode, concurrency=concurrency, link_vendors=True)


def start_handles(db, key: Any, context_name: str, todo: List[tuple], *,
                  skipped: int = 0, mode: str = "build", concurrency: int = 1,
                  link_vendors: bool = False) -> Dict[str, Any]:
    """Queue profiles for a list of (platform, handle) pairs under one job key.

    ``start_many`` builds the list from a market's Top voices; a brand's Voices
    view builds it from the accounts behind the brand's posts and keys the job
    "brand:<id>". ``link_vendors`` records vendor accounts on the market's
    vendor profiles after the run, which only makes sense for a market key.
    """
    if running(key):
        raise RuntimeError("A profiling run for this market is already in progress")
    job: Dict[str, Any] = {
        "state": "running" if todo else "done",
        "market_id": key,
        "total": len(todo), "done": 0, "built": 0, "failed": 0,
        "skipped": skipped, "errors": [], "mode": mode,
        "link_vendors": link_vendors,
        "started_at": _now(), "finished_at": None if todo else _now(),
    }
    _JOBS[key] = job
    if todo:
        job["task"] = asyncio.create_task(
            _run(db, job, context_name, todo, concurrency, mode))
    return status(key)


async def _run(db, job: Dict[str, Any], market_name: str,
               todo: List[tuple], concurrency: int, mode: str = "build") -> None:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(platform: str, handle: str) -> None:
        async with sem:
            try:
                if mode == "reread":
                    prof = await reread_one(db, platform, handle, market_name)
                else:
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
        if job.get("link_vendors"):
            try:
                job["linked"] = (await asyncio.to_thread(
                    link_vendor_accounts, db, job["market_id"]))["linked"]
            except Exception as exc:  # noqa: BLE001 — the profiles stand without the link
                logger.warning("linking vendor accounts failed: %s", exc)
    finally:
        job["state"] = "done"
        job["finished_at"] = _now()
        job["errors"] = job["errors"][:20]
