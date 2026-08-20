"""Market Monitor collection loop.

Vendors collect on their own twelve- or twenty-four-hour cadence. Nothing in a
vendor market moves faster than that in a way anyone could act on: a funding
round, a product launch or a rebrand is no less true half a day later.

Four surfaces, cheapest first:

1. **Feed discovery** — find a vendor's RSS/Atom feeds once and register them.
   Free after the first look.
2. **Page state** — the parts of a site with no feed: pricing, customers,
   partners, careers, trust. A fetch produces a snapshot; a semantic diff
   against the last one is the signal.
3. **LinkedIn company posts** — vendor-authored coverage, via Bright Data.
4. **LinkedIn company profiles** — headcount and followers, weekly. Slowest and
   most expensive per unit of news, so it goes last and least often.

Unlike the SaaS build there is no Redis leader lock: the monolith runs one
process, so the loop cannot race itself across workers.

Every provider call is bracketed by a ``bw_collection_runs`` row, so "failed"
and "nothing new" are different states in the UI rather than a shared silence.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.database import get_database_instance
from app.services import market_collect as mc

logger = logging.getLogger(__name__)

# Short outer sleep so a newly-enabled market starts within minutes; the real
# spacing is the per-(market, source) cadence below.
OUTER_SLEEP_SECONDS = 10 * 60

INITIAL_LOOKBACK = timedelta(days=30)

# Consecutive failures before a source is left alone for a cycle. A provider
# outage should cost one attempt per tick, not one per vendor per tick.
CIRCUIT_THRESHOLD = 3

SOURCE_POSTS = "linkedin_company_post"
SOURCE_PROFILE = "linkedin_company_profile"
SOURCE_PAGES = "vendor_web"
SOURCE_DISCOVERY = "vendor_web_discovery"
SOURCE_CANDIDATES = "funding_discovery"
SOURCE_CRUNCHBASE = mc.CRUNCHBASE_SOURCE
SOURCE_JOBS = mc.JOBS_SOURCE

PROVIDER_BRIGHTDATA = "brightdata"
PROVIDER_INTERNAL = "internal"

_background_task_status: Dict[str, Any] = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "markets_polled": 0,
}


def get_task_status() -> Dict[str, Any]:
    return _background_task_status.copy()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def _enabled() -> bool:
    return (os.getenv("MARKET_MONITORING_ENABLED", "false").strip().lower()
            in ("1", "true", "yes", "on"))


def _max_vendors_per_run() -> int:
    return _env_int("MARKET_MAX_VENDORS_PER_RUN", 20)


def _monthly_budget() -> float:
    try:
        return float(os.getenv("MARKET_MONTHLY_BUDGET_USD", "") or 0)
    except ValueError:
        return 0.0


# The floor. A market source polled faster than this is spending money to learn
# nothing sooner — the whole reason market topics are off the 15-minute loop.
MIN_INTERVAL_HOURS = 6


def source_config(conn, market_id: int) -> Dict[str, Any]:
    """Per-source overrides from ``bw_markets.config['sources']``."""
    cfg = conn.execute(text(
        "SELECT config->'sources' FROM bw_markets WHERE id = :m"),
        {"m": market_id}).scalar()
    return cfg if isinstance(cfg, dict) else {}


def source_enabled(conn, market_id: int, source: str) -> bool:
    """A source is on unless the market says otherwise."""
    entry = source_config(conn, market_id).get(source)
    if isinstance(entry, dict) and entry.get("enabled") is False:
        return False
    return True


def cadence_for(conn, market_id: int, source: str) -> timedelta:
    """The market's own interval for a source, or the default.

    Clamped at the floor: an operator can slow a source down as far as they
    like, and speed it up only to the point where the next reading could
    plausibly differ from the last.
    """
    entry = source_config(conn, market_id).get(source)
    if isinstance(entry, dict) and entry.get("interval_hours"):
        try:
            hours = max(MIN_INTERVAL_HOURS, int(entry["interval_hours"]))
            return timedelta(hours=hours)
        except (TypeError, ValueError):
            pass
    return cadence(source)


def cadence(source: str) -> timedelta:
    """Default hours between runs of a source.

    Two knobs, not eight. Posts and pages move on the fast cadence; profiles
    and rediscovery on the slow one, multiplied out because a headcount that
    changes by one person a week does not repay a daily reading.
    """
    fast = timedelta(hours=_env_int("MARKET_POLL_INTERVAL_HOURS", 12))
    slow = timedelta(hours=_env_int("MARKET_SLOW_POLL_INTERVAL_HOURS", 24))
    return {
        SOURCE_POSTS: fast,
        SOURCE_PAGES: fast,
        SOURCE_PROFILE: slow * 7,     # weekly
        SOURCE_CRUNCHBASE: slow * 7,  # weekly — rounds do not close daily
        SOURCE_JOBS: slow * 3,        # twice weekly — the spec's hiring signal
        SOURCE_CANDIDATES: slow,      # daily — reads what we already collected
        SOURCE_DISCOVERY: slow * 30,  # monthly, plus after a redirect
    }.get(source, slow)


# ---------------------------------------------------------------------------
# Scheduling state, read from the run log rather than a second table
# ---------------------------------------------------------------------------

def _last_success(conn, market_id: int, source: str) -> Optional[datetime]:
    return conn.execute(text("""
        SELECT MAX(started_at) FROM bw_collection_runs
        WHERE market_id = :m AND source = :s AND status = 'succeeded'
    """), {"m": market_id, "s": source}).scalar()


def _in_flight(conn, market_id: int, source: str) -> bool:
    """Whether a batch for this source is already with the provider.

    Without this the cadence check only looks at the last *success*, so a job
    that takes longer than one tick looks overdue and fires again — two paid
    batches for the same twelve-hour window. Observed once: run 8 was still
    collecting when run 9 was queued ten minutes later.
    """
    return bool(conn.execute(text("""
        SELECT 1 FROM bw_collection_runs
        WHERE market_id = :m AND source = :s AND status IN ('queued', 'running')
        LIMIT 1
    """), {"m": market_id, "s": source}).fetchone())


def _is_due(conn, market_id: int, source: str, now: datetime) -> Optional[datetime]:
    """``since`` for this source, or None when it is not due yet."""
    if not source_enabled(conn, market_id, source):
        return None
    if _in_flight(conn, market_id, source):
        return None
    last = _last_success(conn, market_id, source)
    if last is None:
        return now - INITIAL_LOOKBACK
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now - last < cadence_for(conn, market_id, source):
        return None
    return last


# How long an open circuit stays open before it allows one probe. Without this
# the breaker deadlocks: it opens after N failures, a success is the only thing
# that closes it, and it blocks the attempt that would produce one. A fixed bug
# could then never recover without someone editing the database.
CIRCUIT_COOLDOWN = timedelta(hours=1)


def _circuit_open(conn, market_id: int, source: str) -> bool:
    """True when the last few runs all failed and the cooldown has not elapsed.

    Half-open after ``CIRCUIT_COOLDOWN``: one attempt is allowed through, and
    its outcome decides whether the circuit closes or reopens.
    """
    rows = conn.execute(text("""
        SELECT status, started_at FROM bw_collection_runs
        WHERE market_id = :m AND source = :s
          AND status IN ('succeeded','failed')
        ORDER BY started_at DESC LIMIT :n
    """), {"m": market_id, "s": source, "n": CIRCUIT_THRESHOLD}).fetchall()
    if len(rows) < CIRCUIT_THRESHOLD or any(r[0] != "failed" for r in rows):
        return False

    last_failure = rows[0][1]
    if last_failure is None:
        return True
    if last_failure.tzinfo is None:
        last_failure = last_failure.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last_failure >= CIRCUIT_COOLDOWN:
        logger.info("market %s: %s circuit half-open, allowing one attempt",
                    market_id, source)
        return False
    return True


def _budget_blocks(conn, market_id: int, name: str) -> bool:
    """Whether paid collection should pause. Warns on the way up.

    Only paid sources consult this. Feed discovery and page fetches cost
    bandwidth, not provider credits, so a budget freeze must not also blind the
    market to its vendors' own websites.
    """
    cap = _monthly_budget()
    if cap <= 0:
        return False
    spent = float(conn.execute(text("""
        SELECT COALESCE(SUM(cost_amount), 0) FROM bw_collection_runs
        WHERE market_id = :m AND started_at >= date_trunc('month', NOW())
    """), {"m": market_id}).scalar() or 0.0)
    ratio = spent / cap
    if ratio >= 1.0:
        logger.warning("market %s (%s): monthly provider budget exhausted "
                       "(%.2f/%.2f) — paid collection paused", market_id, name,
                       spent, cap)
        return True
    if ratio >= 0.9:
        logger.warning("market %s (%s): 90%% of provider budget used (%.2f/%.2f)",
                       market_id, name, spent, cap)
    elif ratio >= 0.7:
        logger.info("market %s (%s): 70%% of provider budget used (%.2f/%.2f)",
                    market_id, name, spent, cap)
    return False


def _claim_manual_runs(conn, market_id: int) -> Dict[str, int]:
    """Rows the manual-run endpoint queued, one per source.

    The endpoint returns 202 with a durable row rather than doing the work in
    the request, so this is where that row is picked up.
    """
    rows = conn.execute(text("""
        SELECT id, source FROM bw_collection_runs
        WHERE market_id = :m AND status = 'queued' AND job_id IS NULL
        ORDER BY started_at
    """), {"m": market_id}).fetchall()
    claimed: Dict[str, int] = {}
    for run_id, source in rows:
        if source in claimed:
            # A second manual request for a source already claimed this tick
            # would duplicate the batch. Fold it into the first.
            conn.execute(text("""
                UPDATE bw_collection_runs
                SET status = 'cancelled', completed_at = NOW(),
                    error = 'superseded by run ' || :keep
                WHERE id = :r
            """), {"keep": str(claimed[source]), "r": run_id})
            continue
        conn.execute(text(
            "UPDATE bw_collection_runs SET status = 'running' WHERE id = :r"),
            {"r": run_id})
        claimed[source] = run_id
    conn.commit()
    return claimed


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

async def tick() -> Dict[str, Any]:
    """One pass over every enabled market. Safe to call often — a no-op cycle
    is a handful of indexed SELECTs."""
    summary = {"markets": 0, "runs": 0, "errors": 0}
    conn = get_database_instance()._temp_get_connection()
    try:
        markets = conn.execute(text(
            "SELECT id, name FROM bw_markets WHERE enabled = TRUE ORDER BY id"
        )).mappings().all()
        now = datetime.now(timezone.utc)
        for market in markets:
            summary["markets"] += 1
            try:
                summary["runs"] += await _poll_market(conn, dict(market), now)
            except Exception:
                conn.rollback()
                summary["errors"] += 1
                logger.exception("market %s poll failed", market["id"])
    finally:
        conn.close()
    return summary


async def _poll_market(conn, market: Dict[str, Any], now: datetime) -> int:
    market_id = market["id"]
    manual = _claim_manual_runs(conn, market_id)

    vendors = [dict(r) for r in conn.execute(text("""
        SELECT mb.brand_id, b.display_name
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.collection_enabled
          AND mb.role <> 'excluded'
        ORDER BY mb.sort_order
    """), {"m": market_id}).mappings().all()]
    if not vendors:
        return 0

    runs = 0
    # Before spending on anything new, claim what is already paid for.
    runs += await _reconcile_open_jobs(conn, market)
    runs += _discover_candidates(conn, market, now)
    runs += await _discover_feeds(conn, market, vendors, now,
                                  forced_run_id=manual.get(SOURCE_DISCOVERY))
    runs += await _poll_pages(conn, market, vendors, now,
                              forced_run_id=manual.get(SOURCE_PAGES))

    from app.services.brightdata_linkedin import linkedin_enabled

    if linkedin_enabled():
        # A manual run is an operator decision; the budget cap is not
        # negotiable by it, because the point of the cap is that nothing
        # spends past it.
        if _budget_blocks(conn, market_id, market["name"]):
            for source in (SOURCE_POSTS, SOURCE_PROFILE):
                run_id = manual.get(source)
                if run_id:
                    mc.close_run(conn, run_id, status="failed",
                                 error="monthly provider budget exhausted")
            conn.commit()
        else:
            runs += await _poll_linkedin(conn, market, SOURCE_POSTS, now,
                                         forced_run_id=manual.get(SOURCE_POSTS))
            runs += await _poll_linkedin(conn, market, SOURCE_PROFILE, now,
                                         forced_run_id=manual.get(SOURCE_PROFILE))
            runs += await _poll_dataset(conn, market, SOURCE_CRUNCHBASE, now,
                                        forced_run_id=manual.get(SOURCE_CRUNCHBASE))
            runs += await _poll_dataset(conn, market, SOURCE_JOBS, now,
                                        forced_run_id=manual.get(SOURCE_JOBS))
    return runs


# ── Claiming jobs the callback never delivered ──────────────────────────────

# How long to let the webhook do its job before polling the provider. Long
# enough that a healthy delivery is never raced, short enough that a lost one
# is claimed within a cycle.
RECONCILE_AFTER_MINUTES = 10


async def _reconcile_open_jobs(conn, market: Dict[str, Any]) -> int:
    """Claim finished provider jobs whose callback never arrived.

    The webhook is an optimisation, not a guarantee: a delivery can be dropped,
    refused while the app restarts, or simply never sent. Records are billed
    when the provider collects them, so a run stuck in ``running`` is money
    already spent sitting behind a message that is not coming. The job id on
    the run row is what makes it recoverable.
    """
    from app.services.brightdata_linkedin import (
        BrightDataError, LinkedInDatasetClient, api_key,
    )

    rows = conn.execute(text("""
        SELECT id, source, job_id FROM bw_collection_runs
        WHERE market_id = :m AND provider = :p AND job_id IS NOT NULL
          AND status IN ('queued', 'running')
          AND started_at < NOW() - (:mins || ' minutes')::INTERVAL
        ORDER BY id
    """), {"m": market["id"], "p": PROVIDER_BRIGHTDATA,
           "mins": str(RECONCILE_AFTER_MINUTES)}).fetchall()
    if not rows:
        return 0

    key = api_key()
    if not key:
        return 0
    client = LinkedInDatasetClient(key)
    claimed = 0

    for run_id, source, job_id in rows:
        try:
            progress = await client.snapshot_status(job_id)
        except BrightDataError as e:
            logger.warning("market %s: progress check failed for %s: %s",
                           market["id"], job_id, e)
            continue
        state = str(progress.get("status") or "").lower()
        if state in ("running", "collecting", "building", "pending"):
            continue
        if state not in ("ready", "done", "finished"):
            mc.close_run(conn, run_id, status="failed",
                         error=f"provider reported {state or 'unknown'}")
            conn.commit()
            continue

        try:
            records = await client.fetch_snapshot(job_id)
        except BrightDataError as e:
            logger.warning("market %s: snapshot fetch failed for %s: %s",
                           market["id"], job_id, e)
            continue

        run = mc.load_run(conn, run_id)
        try:
            result = mc.ingest_for_source(conn, run=run, records=records)
            mc.close_run(
                conn, run_id,
                status=mc.outcome_status(len(records), result.get("stored", 0),
                                         result.get("provider_errors", 0)),
                received=len(records),
                new=result.get("stored", 0),
                skipped=(result.get("unchanged", 0) + result.get("unmatched", 0)
                         + result.get("dropped", 0)),
            )
            conn.commit()
            claimed += 1
            logger.info("market %s: claimed %s job %s by polling — %s",
                        market["id"], source, job_id, result)
        except Exception as e:
            conn.rollback()
            mc.close_run(conn, run_id, status="failed", error=str(e))
            conn.commit()
    return claimed


# ── New entrants ────────────────────────────────────────────────────────────

def _discover_candidates(conn, market: Dict[str, Any], now: datetime) -> int:
    """Scan the market's own funding coverage for vendors we do not have.

    Costs nothing external: it reads articles already collected. Daily is
    plenty — a funding round stays newsworthy for longer than that.
    """
    from app.services import market_discovery as md

    if _is_due(conn, market["id"], SOURCE_CANDIDATES, now) is None:
        return 0
    run_id = mc.open_run(conn, market_id=market["id"], source=SOURCE_CANDIDATES,
                         provider=PROVIDER_INTERNAL)
    try:
        result = md.discover_funding_candidates(conn, market["id"], days=14)
        mc.close_run(conn, run_id, status="succeeded",
                     received=result.get("scanned", 0),
                     new=result.get("candidates", 0),
                     error=result.get("error"))
        conn.commit()
        if result.get("candidates"):
            logger.info("market %s: %d candidate vendors from funding coverage",
                        market["id"], result["candidates"])
    except Exception as e:
        conn.rollback()
        mc.close_run(conn, run_id, status="failed", error=str(e))
        conn.commit()
    return 1


# ── Feeds ───────────────────────────────────────────────────────────────────

async def _discover_feeds(conn, market: Dict[str, Any], vendors: List[dict],
                          now: datetime, forced_run_id: Optional[int] = None) -> int:
    """Record each vendor's RSS/Atom feeds and the pages worth watching."""
    from app.collectors import vendor_web_collector as vw

    if forced_run_id is None:
        if _is_due(conn, market["id"], SOURCE_DISCOVERY, now) is None:
            return 0
        run_id = mc.open_run(conn, market_id=market["id"],
                             source=SOURCE_DISCOVERY, provider=PROVIDER_INTERNAL)
    else:
        run_id = forced_run_id

    # Feeds land under the market's collection topic, so vendor blog posts
    # join the same corpus the keyword group fills and get the same ontology.
    topic_name = conn.execute(text(
        "SELECT config->'collection'->>'topic_name' FROM bw_markets WHERE id = :m"),
        {"m": market["id"]}).scalar() or f"Market Monitoring {market['name']}"

    found = failed = 0
    try:
        for vendor in vendors[: _max_vendors_per_run()]:
            domain = conn.execute(text("""
                SELECT normalized_value FROM bw_vendor_identifiers
                WHERE brand_id = :b AND kind = 'domain' AND valid_to IS NULL
                LIMIT 1
            """), {"b": vendor["brand_id"]}).scalar()
            if not domain:
                continue
            try:
                sources = await vw.discover_sources(domain, probe_pages=True)
            except Exception:
                failed += 1
                logger.debug("feed discovery failed for %s", domain, exc_info=True)
                continue
            # Register the feeds so the existing RSS collector polls them.
            # Recording them only in the baseline would leave a vendor's blog
            # "discovered" and never read.
            for feed_url in sources.feeds:
                conn.execute(text("""
                    INSERT INTO rss_feeds (name, url, topic, description, is_active)
                    SELECT :n, :u, :t, :d, TRUE
                    WHERE NOT EXISTS (SELECT 1 FROM rss_feeds WHERE url = :u)
                """), {"n": f"{vendor['display_name']} feed"[:255], "u": feed_url,
                       "t": topic_name[:255],
                       "d": f"Discovered on {sources.domain} by Market Monitor"})
                found += 1

            # Remember what is worth fetching so the page poll does not
            # re-probe a whole site every twelve hours.
            conn.execute(text("""
                UPDATE bw_market_brands
                SET baseline = baseline || CAST(:p AS JSONB), updated_at = NOW()
                WHERE market_id = :m AND brand_id = :b
            """), {"m": market["id"], "b": vendor["brand_id"],
                   "p": json.dumps({
                       "web_pages": sources.pages,
                       "web_feeds": sources.feeds,
                       "web_discovered_at": now.isoformat(),
                   }, default=str)})
            await asyncio.sleep(0.5)
        mc.close_run(conn, run_id, status="succeeded", new=found, skipped=failed)
        conn.commit()
    except Exception as e:
        conn.rollback()
        mc.close_run(conn, run_id, status="failed", error=str(e))
        conn.commit()
    return 1


# ── Page state ──────────────────────────────────────────────────────────────

async def _poll_pages(conn, market: Dict[str, Any], vendors: List[dict],
                      now: datetime, forced_run_id: Optional[int] = None) -> int:
    from app.collectors import vendor_web_collector as vw

    if forced_run_id is None:
        if _is_due(conn, market["id"], SOURCE_PAGES, now) is None:
            return 0
        if _circuit_open(conn, market["id"], SOURCE_PAGES):
            return 0
        run_id = mc.open_run(conn, market_id=market["id"], source=SOURCE_PAGES,
                             provider=PROVIDER_INTERNAL)
    else:
        run_id = forced_run_id

    fetched = changed = unchanged = errors = 0
    try:
        for vendor in vendors[: _max_vendors_per_run()]:
            pages = conn.execute(text("""
                SELECT baseline->'web_pages' FROM bw_market_brands
                WHERE market_id = :m AND brand_id = :b
            """), {"m": market["id"], "b": vendor["brand_id"]}).scalar() or []
            for page in pages:
                if not isinstance(page, dict) or not page.get("url"):
                    continue
                url = page["url"]
                prior = conn.execute(text("""
                    SELECT data, content_hash FROM bw_vendor_snapshots
                    WHERE brand_id = :b AND provider_item_id = :u
                      AND snapshot_type = 'page_state'
                    ORDER BY observed_at DESC LIMIT 1
                """), {"b": vendor["brand_id"], "u": url}).first()
                prior_data = (prior[0] if prior else None) or {}
                result = await vw.fetch_page(
                    url, etag=prior_data.get("etag"),
                    last_modified=prior_data.get("last_modified"),
                    prior_hash=prior[1] if prior else None,
                )
                fetched += 1
                if result.error:
                    errors += 1
                    continue
                if not result.changed:
                    unchanged += 1
                    continue
                diff = vw.diff_pages(prior_data.get("text"), result.text)
                if not diff["material"]:
                    # Reflow, not news. Storing it would put a change on the
                    # vendor's timeline nobody could point at.
                    unchanged += 1
                    continue
                mc.store_snapshot(
                    conn, market_id=market["id"], brand_id=vendor["brand_id"],
                    source=SOURCE_PAGES, snapshot_type="page_state",
                    provider_item_id=url,
                    data={"url": result.url, "kind": page.get("kind"),
                          "title": result.title, "text": result.text,
                          "etag": result.etag,
                          "last_modified": result.last_modified,
                          "diff": diff, "http_status": result.status},
                    observed_at=result.fetched_at, run_id=run_id,
                )
                changed += 1
                await asyncio.sleep(0.3)  # courtesy spacing on one host
        mc.close_run(conn, run_id, status="succeeded", received=fetched,
                     new=changed, skipped=unchanged + errors)
        conn.commit()
    except Exception as e:
        conn.rollback()
        mc.close_run(conn, run_id, status="failed", error=str(e))
        conn.commit()
    return 1


# ── Crunchbase and job listings ─────────────────────────────────────────────

async def _poll_dataset(conn, market: Dict[str, Any], source: str,
                        now: datetime, forced_run_id: Optional[int] = None) -> int:
    """Queue one Bright Data batch for a non-LinkedIn-post dataset.

    Same shape as ``_poll_linkedin``: the run row is committed before the
    trigger, because a callback that arrives with nowhere to land is a batch
    paid for and lost.
    """
    from app.routes.market_monitor_routes import callback_url
    from app.services.brightdata_linkedin import (
        BrightDataError, LinkedInDatasetClient, api_key, webhook_auth_value,
    )

    if forced_run_id is None:
        if _is_due(conn, market["id"], source, now) is None:
            return 0
        if _circuit_open(conn, market["id"], source):
            return 0

    key = api_key()
    if not key:
        return 0

    if source == SOURCE_CRUNCHBASE:
        mc.seed_crunchbase_urls(conn, market["id"])
        conn.commit()
        urls = list(mc.crunchbase_url_map(conn, market["id"]).keys())
    else:
        urls = list(mc.linkedin_url_map(conn, market["id"])[0].keys())
    urls = urls[: _max_vendors_per_run()]
    if not urls:
        if forced_run_id:
            mc.close_run(conn, forced_run_id, status="succeeded",
                         error="no vendors with a usable URL for this source")
            conn.commit()
        return 0

    run_id = forced_run_id or mc.open_run(
        conn, market_id=market["id"], source=source,
        provider=PROVIDER_BRIGHTDATA, status="queued")
    conn.commit()

    client = LinkedInDatasetClient(key)
    try:
        if source == SOURCE_CRUNCHBASE:
            result = await client.trigger_crunchbase(
                urls, webhook_url=callback_url(run_id),
                webhook_auth=webhook_auth_value())
        else:
            result = await client.trigger_jobs(
                urls, webhook_url=callback_url(run_id),
                webhook_auth=webhook_auth_value())
    except BrightDataError as e:
        mc.close_run(conn, run_id, status="failed", error=str(e))
        conn.commit()
        logger.warning("market %s: %s trigger failed: %s", market["id"], source, e)
        return 1

    mc.attach_job(conn, run_id, result.snapshot_id)
    conn.execute(text("""
        UPDATE bw_collection_runs SET status = 'running', request_hash = :rh,
               records_received = :n WHERE id = :r
    """), {"rh": result.request_hash, "n": result.requested, "r": run_id})
    conn.commit()
    logger.info("market %s: queued %s batch %s for %d vendors",
                market["id"], source, result.snapshot_id, result.requested)
    return 1


# ── LinkedIn ────────────────────────────────────────────────────────────────

async def _poll_linkedin(conn, market: Dict[str, Any], source: str,
                         now: datetime, forced_run_id: Optional[int] = None) -> int:
    """Queue one async Bright Data batch for the market's vendors."""
    from app.routes.market_monitor_routes import callback_url
    from app.services.brightdata_linkedin import (
        BrightDataError, LinkedInDatasetClient, api_key, webhook_auth_value,
    )

    since = _is_due(conn, market["id"], source, now)
    if forced_run_id is None:
        if since is None or _circuit_open(conn, market["id"], source):
            return 0
    elif since is None:
        # Forced: no cadence gate, but still only ask for what we have not
        # already collected.
        since = _last_success(conn, market["id"], source) or (now - INITIAL_LOOKBACK)

    key = api_key()
    if not key:
        if forced_run_id:
            mc.close_run(conn, forced_run_id, status="failed",
                         error="no Bright Data key configured")
            conn.commit()
        return 0

    urls = [r[0] for r in conn.execute(text("""
        SELECT i.normalized_value FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
                                 AND mb.market_id = :m
        WHERE i.kind = 'linkedin_company_url' AND i.valid_to IS NULL
          AND mb.collection_enabled AND mb.role <> 'excluded'
        ORDER BY mb.sort_order LIMIT :lim
    """), {"m": market["id"], "lim": _max_vendors_per_run()}).fetchall()]
    if not urls:
        if forced_run_id:
            mc.close_run(conn, forced_run_id, status="succeeded",
                         error="no vendors with a LinkedIn URL and collection enabled")
            conn.commit()
        return 0

    # The run row is committed BEFORE the trigger call. A callback that arrives
    # while we are still awaiting the HTTP response needs a row to land on, and
    # losing a snapshot id means paying for records we can never claim.
    run_id = forced_run_id or mc.open_run(
        conn, market_id=market["id"], source=source,
        provider=PROVIDER_BRIGHTDATA, status="queued")
    conn.commit()

    client = LinkedInDatasetClient(key)
    try:
        if source == SOURCE_POSTS:
            result = await client.trigger_posts(
                urls, since=since, webhook_url=callback_url(run_id),
                webhook_auth=webhook_auth_value())
        else:
            result = await client.trigger_profiles(
                urls, webhook_url=callback_url(run_id),
                webhook_auth=webhook_auth_value())
    except BrightDataError as e:
        mc.close_run(conn, run_id, status="failed", error=str(e))
        conn.commit()
        logger.warning("market %s: %s trigger failed (retryable=%s): %s",
                       market["id"], source, e.retryable, e)
        return 1

    mc.attach_job(conn, run_id, result.snapshot_id)
    conn.execute(text("""
        UPDATE bw_collection_runs
        SET status = 'running', request_hash = :rh, records_received = :n
        WHERE id = :r
    """), {"rh": result.request_hash, "n": result.requested, "r": run_id})
    conn.commit()
    logger.info("market %s: queued %s batch %s for %d vendors",
                market["id"], source, result.snapshot_id, result.requested)
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_market_monitor():
    """Background task registered by the module registry."""
    logger.info("Market Monitor background task started")
    _background_task_status["running"] = True
    while True:
        try:
            if _enabled():
                _background_task_status["last_check_time"] = datetime.now()
                summary = await tick()
                _background_task_status["markets_polled"] = summary["markets"]
                if summary["runs"]:
                    logger.info("Market Monitor: %s", summary)
        except asyncio.CancelledError:
            logger.info("Market Monitor cancelled")
            _background_task_status["running"] = False
            raise
        except Exception as e:
            _background_task_status["last_error"] = str(e)
            logger.exception("Market Monitor cycle failed")
        await asyncio.sleep(OUTER_SLEEP_SECONDS)
