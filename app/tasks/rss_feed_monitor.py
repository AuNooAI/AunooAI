"""
RSS Feed Monitor - Background task for scheduled RSS feed fetching.
Each feed has its own schedule based on check_interval.

Scheduling state and coverage state are kept apart (work packages 1, 2,
16, 21 and 29 of docs/COLLECTOR_DATA_QUALITY_SPEC.md):

- ``last_attempt_at`` (and its alias ``last_checked_at``) say when we last
  tried. ``last_success_at`` says when a try worked. ``coverage_through``
  says how far the feed's content is proven stored, and only moves when a
  run was complete and every item was persisted.
- A failing feed backs off: ``next_poll_at`` moves out by the base
  interval times 2^(n-1), capped at eight times. Twenty hard failures in a
  row (403, 404, 410, DNS, parse) mark it ``needs_attention``; it keeps
  polling at the slow cadence and is never deactivated here.
- Cache validators (ETag, Last-Modified) are written only after every
  entry is stored or queued in ``pending_feed_entries``; otherwise a 304
  on the next poll would hide entries we lost.
- A missing publication date is stored as NULL with ``first_seen_at``
  set, never as the current time.
"""

import json
import logging
import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List, Tuple
from sqlalchemy import text, select, update

from app.database import Database, get_database_instance
from app.database_models import t_rss_feeds, t_rss_feed_monitor_status
from app.collectors.rss_collector import RSSCollector
from app.collectors import rss_collector
from app.collectors import dates
from app.collectors.contracts import (
    CollectionResult, ERR_AUTH, ERR_DNS, ERR_HTTP_4XX, ERR_PARSE, ERR_QUOTA,
    describe_exception, host_of,
)
from app.services.collection_runs import record_run
from app.services.provider_quota import HostGuard

logger = logging.getLogger(__name__)

#: Backoff saturates here: a dead feed is polled at eight times its base
#: interval, not never.
BACKOFF_MAX_MULTIPLIER = 8
#: Hard failures in a row before a feed is flagged for a person to look at.
NEEDS_ATTENTION_AFTER = max(1, int(os.getenv("RSS_NEEDS_ATTENTION_AFTER", "20") or 20))
#: Partial parses in a row before the feed is flagged the same way.
PARSE_PARTIAL_ATTENTION_AFTER = max(1, int(os.getenv("RSS_PARSE_PARTIAL_ATTENTION_AFTER", "10") or 10))
#: Store attempts for a queued entry before we stop trying and say so.
PENDING_MAX_ATTEMPTS = 5
#: New entries stored and enriched per poll of one feed. Everything beyond
#: it is queued durably in ``pending_feed_entries`` and drained on later
#: polls. Without a bound, the first poll after the 50-entry cap was removed
#: pushed a feed's whole archive (UiPath: 1,287 entries) through scraping
#: and enrichment in one go (work package 2's processing budget).
NEW_ENTRIES_PER_POLL = max(1, int(os.getenv("RSS_NEW_ENTRIES_PER_POLL", "100") or 100))
#: Hosts that rate-limit by client address; every tenant on this box shares
#: one budget for them (work package 21).
BUDGETED_HOSTS = ("reddit.com",)

POLL_OK = "ok"
POLL_ERROR = "error"
POLL_NEEDS_ATTENTION = "needs_attention"

STORE_INSERTED = "inserted"
STORE_EXISTING = "existing"
STORE_FAILED = "failed"

# Global status tracking
_monitor_status = {
    "running": False,
    "last_check_time": None,
    "feeds_checked": 0,
    "articles_fetched": 0,
    "last_error": None
}


def get_monitor_status() -> Dict:
    """Get the current status of the RSS feed monitor."""
    return _monitor_status.copy()


# ---------------------------------------------------------------------------
# Pure scheduling helpers. Kept free of the database so the backoff maths
# can be tested on its own.
# ---------------------------------------------------------------------------


def interval_of(feed: Dict) -> timedelta:
    """The feed's configured base polling interval."""
    interval = int(feed.get('check_interval') or 60)
    unit = feed.get('interval_unit') or 'minutes'
    if unit == 'hours':
        return timedelta(hours=interval)
    if unit == 'days':
        return timedelta(days=interval)
    return timedelta(minutes=interval)


def backoff_delay(base: timedelta, consecutive_failures: int) -> timedelta:
    """How long to wait after the n-th consecutive failure: 1x, 2x, 4x,
    8x the base interval, and 8x from then on."""
    n = max(1, int(consecutive_failures or 1))
    return base * min(2 ** (n - 1), BACKOFF_MAX_MULTIPLIER)


def is_hard_failure(result: CollectionResult) -> bool:
    """A failure that will not fix itself: 403, 404, 410, DNS, or a parse
    error. Timeouts, 5xx and 429 are the host or the network having a bad
    moment and do not count towards needs_attention."""
    if not result.failed:
        return False
    code = result.error_code
    if code in (ERR_DNS, ERR_PARSE, ERR_AUTH):
        return True
    if code == ERR_HTTP_4XX and not result.retryable:
        return True
    return False


def is_due(feed: Dict, now: datetime) -> bool:
    """Due when ``next_poll_at`` has passed; for a feed that has none yet,
    when the base interval has passed since the last attempt."""
    next_poll = _aware(feed.get('next_poll_at'))
    if next_poll is not None:
        return now >= next_poll
    last = _aware(feed.get('last_attempt_at') or feed.get('last_checked_at'))
    if last is None:
        return True
    return now >= last + interval_of(feed)


def _aware(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _budgeted_host(feed_url: str) -> Optional[str]:
    host = (host_of(feed_url) or "").lower()
    for budgeted in BUDGETED_HOSTS:
        if host == budgeted or host.endswith("." + budgeted):
            return budgeted
    return None


class RSSFeedMonitor:
    """Monitor for scheduled RSS feed fetching."""

    def __init__(self, db: Database):
        self.db = db
        self.check_interval_seconds = 60  # Check for due feeds every minute
        #: Why the last _store_article call returned "failed", for the
        #: pending-entry row. The outcome itself stays a plain string.
        self._last_store_error: Optional[str] = None

    async def get_due_feeds(self) -> List[Dict]:
        """Get feeds that are due for checking based on their individual schedules."""
        conn = None
        try:
            now = datetime.now(timezone.utc)

            # Query for active feeds that are due
            query = select(t_rss_feeds).where(t_rss_feeds.c.is_active == True)

            conn = self.db._temp_get_connection()
            result = conn.execute(query)
            feeds = [dict(row._mapping) for row in result]

            return [feed for feed in feeds if is_due(feed, now)]

        except Exception as e:
            logger.error(f"Error getting due feeds: {e}")
            return []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # -- feed state writes ----------------------------------------------

    def _update_feed(self, feed_id: int, values: Dict[str, Any]) -> None:
        """One UPDATE on the feed row. Every state change goes through here
        so a test can read what would have been written."""
        values = dict(values)
        values.setdefault('updated_at', datetime.now(timezone.utc))
        stmt = update(t_rss_feeds).where(t_rss_feeds.c.id == feed_id).values(**values)
        conn = self.db._temp_get_connection()
        try:
            conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    def _write_run(self, feed_id: int, result: CollectionResult,
                   checkpoint_before, checkpoint_after) -> None:
        try:
            record_run(self.db, result, scope_kind="rss_feed", scope_id=str(feed_id),
                       checkpoint_before=checkpoint_before, checkpoint_after=checkpoint_after)
        except Exception as exc:                                      # noqa: BLE001
            logger.warning("run record not written for feed %s: %s", feed_id, exc)

    def _failure_values(self, feed: Dict, result: CollectionResult, now: datetime) -> Dict[str, Any]:
        """The feed-row update for a failed attempt: counters, backoff,
        and needs_attention after enough hard failures. The coverage
        checkpoint and validators are not touched; backoff is scheduling
        state, not coverage state."""
        n = int(feed.get('consecutive_error_count') or 0) + 1
        message = (result.error_message or result.error_code or "failed")[:500]
        status = POLL_ERROR
        reason = feed.get('needs_attention_reason')
        if feed.get('polling_status') == POLL_NEEDS_ATTENTION:
            # Already flagged; a timeout in between does not clear it.
            status = POLL_NEEDS_ATTENTION
        elif n >= NEEDS_ATTENTION_AFTER and is_hard_failure(result):
            status = POLL_NEEDS_ATTENTION
            reason = f"{n} consecutive failures; last: {message}"[:1000]
            logger.warning("feed %s needs attention after %d failures: %s",
                           feed.get('id'), n, message)
        values = {
            'last_attempt_at': now,
            'last_checked_at': now,
            'last_failed_at': now,
            'consecutive_error_count': n,
            'polling_status': status,
            'needs_attention_reason': reason if status == POLL_NEEDS_ATTENTION else None,
            'last_error': message,
            'next_poll_at': now + backoff_delay(interval_of(feed), n),
            'updated_at': now,
        }
        if not feed.get('first_failed_at'):
            values['first_failed_at'] = now
        return values

    def _success_values(self, feed: Dict, now: datetime) -> Dict[str, Any]:
        """The parts of a successful attempt that every success shares:
        counters reset, base cadence restored."""
        return {
            'last_attempt_at': now,
            'last_checked_at': now,
            'last_success_at': now,
            'consecutive_error_count': 0,
            'polling_status': POLL_OK,
            'first_failed_at': None,
            'last_failed_at': None,
            'needs_attention_reason': None,
            'last_error': None,
            'next_poll_at': now + interval_of(feed),
            'updated_at': now,
        }

    # -- the poll ---------------------------------------------------------

    async def fetch_feed(self, feed: Dict) -> int:
        """Poll one feed: replay what is queued, fetch, store, and record
        what happened. Returns the number of newly inserted articles."""
        feed_id = feed['id']
        feed_url = feed['url']
        topic = feed['topic']
        feed_name = feed['name']
        last_article_date = feed.get('last_article_date')
        relevance_threshold = feed.get('relevance_threshold', 0)
        default_factual_reporting = feed.get('default_factual_reporting')
        coverage_before = _aware(feed.get('coverage_through'))
        now = datetime.now(timezone.utc)

        # Entries a previous poll could not store get another go first, so
        # a queued entry never waits behind a feed that is now failing.
        replayed: List[Dict] = []
        try:
            replayed = await self._replay_pending(feed_id, topic)
        except Exception as exc:                                      # noqa: BLE001
            logger.warning("pending replay failed for feed %s: %s", feed_id,
                           describe_exception(exc))

        async def enrich_replayed() -> int:
            # Entries stored from the queue still need enrichment even when
            # this poll's fetch goes nowhere.
            if replayed:
                try:
                    await self._run_auto_ingest(replayed, topic, relevance_threshold,
                                                default_factual_reporting)
                except Exception as exc:                              # noqa: BLE001
                    logger.warning("enrichment of replayed entries failed for feed %s: %s",
                                   feed_id, describe_exception(exc))
            return len(replayed)

        # Shared host budget: reddit rate-limits the box, not the tenant.
        host_guard = None
        budgeted = _budgeted_host(feed_url)
        if budgeted:
            host_guard = HostGuard(budgeted)
            blocked = host_guard.check()
            if blocked is not None:
                blocked.provider = "rss"
                blocked.scope = feed_url
                blocked.started_at = now
                until = _aware(blocked.diagnostics.get("quota_exhausted_until"))
                logger.info("feed '%s' skipped: %s", feed_name, blocked.error_message)
                # Not the feed's fault: no backoff counters, no error status.
                self._update_feed(feed_id, {
                    'last_attempt_at': now,
                    'last_checked_at': now,
                    'last_error': (blocked.error_message or "quota_exhausted")[:500],
                    'next_poll_at': until if until and until > now else now + interval_of(feed),
                    'updated_at': now,
                })
                self._write_run(feed_id, blocked, coverage_before, coverage_before)
                return await enrich_replayed()

        collector = RSSCollector()
        logger.info(f"Fetching RSS feed '{feed_name}' (ID: {feed_id})")
        try:
            result = await collector.fetch_feed_result(
                feed_url=feed_url,
                topic=topic,
                since=last_article_date,
                etag=feed.get('etag'),
                last_modified=feed.get('last_modified'),
            )
        except Exception as exc:                                      # noqa: BLE001
            result = CollectionResult.from_exception(exc, host=host_of(feed_url))
        result.provider = "rss"
        result.scope = feed_url
        if result.started_at is None:
            result.started_at = now

        if host_guard is not None and result.diagnostics.get("http_status") == 429:
            paused_until = host_guard.rate_limited(result.diagnostics.get("retry_after"))
            if paused_until:
                result.diagnostics["host_paused_until"] = paused_until.isoformat()

        if result.failed:
            logger.error(f"Error fetching feed '{feed_name}': {result.error_message}")
            values = self._failure_values(feed, result, now)
            if result.error_code == ERR_QUOTA and result.diagnostics.get("host_paused_until"):
                paused = _aware(result.diagnostics["host_paused_until"])
                if paused and paused > values['next_poll_at']:
                    values['next_poll_at'] = paused
            if replayed:
                values['articles_fetched'] = t_rss_feeds.c.articles_fetched + len(replayed)
            self._update_feed(feed_id, values)
            self._write_run(feed_id, result, coverage_before, coverage_before)
            return await enrich_replayed()

        try:
            inserted_count, enriched_count = await self._persist_result(
                feed, result, now, replayed, relevance_threshold, default_factual_reporting)
        except Exception as exc:                                      # noqa: BLE001
            # Our own storage path broke, not the feed. Say so in the row
            # but do not back the feed off for it, and do not move coverage.
            message = describe_exception(exc, host=host_of(feed_url))
            logger.error("storing feed '%s' failed: %s", feed_name, message)
            result.status = "partial"
            result.coverage_complete = False
            result.error_code = result.error_code or "storage"
            result.error_message = message
            self._update_feed(feed_id, {
                'last_attempt_at': now, 'last_checked_at': now,
                'last_error': message[:500], 'next_poll_at': now + interval_of(feed),
                'updated_at': now,
            })
            self._write_run(feed_id, result, coverage_before, coverage_before)
            return await enrich_replayed()
        return inserted_count

    async def _persist_result(self, feed: Dict, result: CollectionResult, now: datetime,
                              replayed: List[Dict], relevance_threshold,
                              default_factual_reporting) -> Tuple[int, int]:
        """Store a successful or partial fetch and write the feed state.

        The data checkpoint (``coverage_through``, ``last_article_date``)
        moves only when the run was complete and every insert worked.
        Validators are committed only when every entry was stored or
        queued durably in this poll.
        """
        feed_id = feed['id']
        feed_name = feed['name']
        topic = feed['topic']
        coverage_before = _aware(feed.get('coverage_through'))
        values = self._success_values(feed, now)
        collector = RSSCollector()

        if result.diagnostics.get("not_modified"):
            logger.info("Feed '%s' not modified", feed_name)
            # Nothing new to prove; the checkpoint stays where it was. The
            # validators we hold are still right, so re-committing them is
            # harmless, and we keep whatever the 304 echoed back.
            if result.proposed_validators:
                values.update(self._validator_values(result.proposed_validators))
            values['parse_partial_count'] = 0
            inserted_total = len(replayed)
            values['articles_fetched'] = t_rss_feeds.c.articles_fetched + inserted_total
            self._update_feed(feed_id, values)
            self._write_run(feed_id, result, coverage_before, coverage_before)
            return inserted_total, 0

        articles = list(result.items)
        logger.info(f"Found {len(articles)} articles from feed '{feed_name}'")

        inserted: List[Dict] = []
        failed_items: List[Tuple[Dict, str]] = []
        newest_date: Optional[datetime] = None
        enriched_count = 0

        if articles:
            # A feed that has just re-stamped its whole archive hands us
            # old posts with this week's date. Checked against the
            # Wayback Machine only for URLs we do not hold yet and only
            # when the feed shows a close-dated batch — see the note in
            # rss_collector. Done before storing, so the stored date is
            # the bounded one.
            # Only this poll's share of new entries is stored and enriched;
            # the rest is queued for later polls so one long feed cannot
            # spend an hour of scraping and model calls in a single cycle.
            budget = max(0, NEW_ENTRIES_PER_POLL - len(replayed))
            this_poll, deferred_items, fresh = [], [], []
            for a in articles:
                url = (a.get('url') or '').strip()
                if not url:
                    this_poll.append(a)
                    continue
                if len(fresh) >= budget:
                    deferred_items.append(a)
                    continue
                if not self.db.facade.article_exists((url,)):
                    fresh.append(a)
                this_poll.append(a)
            if deferred_items:
                queued = self._queue_pending(
                    feed_id, [(a, "deferred: per-poll budget") for a in deferred_items],
                    deferred=True)
                result.counts.add(deferred=queued)
                result.diagnostics["deferred_backlog"] = len(deferred_items)
                logger.info("Feed '%s': %d entries beyond this poll's budget of %d queued for later polls",
                            feed_name, len(deferred_items), budget)
            articles = this_poll

            if rss_collector.restamp_check_enabled():
                try:
                    fixed = await rss_collector.bound_restamped_dates(fresh)
                    if fixed:
                        logger.info("Feed '%s': %d re-stamped date(s) "
                                    "bounded by first capture", feed_name, fixed)
                except Exception as check_error:              # noqa: BLE001
                    logger.warning("re-stamp check skipped for '%s': %s",
                                   feed_name, check_error)

            # Where each publisher sits, resolved once for the batch.
            # A feed is usually a single domain, so this is one registry
            # read. It has to happen at insert: nothing downstream can
            # work out a publisher's country from a stored row, and the
            # keyword-monitor path never passes through here.
            # Off the event loop: a domain the registry has never seen
            # costs a synchronous model call, and this task shares the
            # loop with every web request on the tenant.
            countries = await asyncio.to_thread(self._resolve_countries, articles)

            for article in articles:
                outcome = await self._store_article(article, topic, countries)
                if outcome == STORE_INSERTED:
                    inserted.append(article)
                    result.counts.add(inserted=1)
                elif outcome == STORE_EXISTING:
                    result.counts.add(duplicate=1)
                else:
                    failed_items.append((article, self._last_store_error or "store failed"))
                pub_date = collector._parse_date(article.get('published_date'))
                if pub_date and (newest_date is None or pub_date > newest_date):
                    newest_date = pub_date

        if failed_items:
            queued = self._queue_pending(feed_id, failed_items)
            result.counts.add(deferred=queued)
            result.diagnostics["failed_inserts"] = len(failed_items)
            result.diagnostics["queued_pending"] = queued
            if result.status == "success":
                # Items we could not store are incomplete work, not done.
                result.status = "partial"
                result.coverage_complete = False
                result.retryable = True
            result.error_code = result.error_code or "storage"
            result.error_message = result.error_message or failed_items[0][1]

        to_enrich = replayed + inserted
        if to_enrich:
            enriched_count = await self._run_auto_ingest(
                to_enrich, topic, relevance_threshold, default_factual_reporting)

        # -- feed state --------------------------------------------------
        inserted_total = len(inserted) + len(replayed)
        values['articles_fetched'] = t_rss_feeds.c.articles_fetched + inserted_total
        values['articles_enriched'] = t_rss_feeds.c.articles_enriched + enriched_count

        checkpoint_after = coverage_before
        if result.may_advance_checkpoint and not failed_items:
            checkpoint_after = result.interval_end or now
            values['coverage_through'] = checkpoint_after
            if newest_date is not None:
                values['last_article_date'] = newest_date

        if not failed_items and not result.parse_partial and result.proposed_validators:
            values.update(self._validator_values(result.proposed_validators))

        if result.parse_partial:
            count = int(feed.get('parse_partial_count') or 0) + 1
            values['parse_partial_count'] = count
            values['last_error'] = (f"parse_partial: {result.diagnostics.get('bozo', '')}"
                                    f" ({result.diagnostics.get('entries_recovered', len(articles))}"
                                    f" entries recovered)")[:500]
            if count >= PARSE_PARTIAL_ATTENTION_AFTER:
                values['polling_status'] = POLL_NEEDS_ATTENTION
                values['needs_attention_reason'] = (
                    f"parse_partial for {count} consecutive polls; last: "
                    f"{result.diagnostics.get('bozo', '')}")[:1000]
        else:
            values['parse_partial_count'] = 0

        if failed_items:
            values['last_error'] = (f"{len(failed_items)} entries could not be stored and were "
                                    f"queued; first: {failed_items[0][1]}")[:500]

        self._update_feed(feed_id, values)
        self._write_run(feed_id, result, coverage_before, checkpoint_after)
        return inserted_total, enriched_count

    @staticmethod
    def _validator_values(proposed: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if 'etag' in proposed:
            out['etag'] = proposed.get('etag')
        if 'last_modified' in proposed:
            out['last_modified'] = proposed.get('last_modified')
        return out

    # -- pending entries (work package 16) ---------------------------------

    def _queue_pending(self, feed_id: int, failed_items: List[Tuple[Dict, str]],
                       *, deferred: bool = False) -> int:
        """Queue entries that could not be stored so a later poll can retry
        them, and so validators can be committed without losing them.
        ``deferred`` rows were never attempted (per-poll budget) and start
        at zero attempts. Returns how many rows were written."""
        queued = 0
        first_attempts = 0 if deferred else 1
        conn = None
        try:
            conn = self.db._temp_get_connection()
            for article, error in failed_items:
                key = (article.get('url') or '').strip()
                if not key:
                    continue
                payload = {k: v for k, v in article.items() if not str(k).startswith('_')}
                conn.execute(text("""
                    INSERT INTO pending_feed_entries (feed_id, entry_key, payload, attempts, last_error)
                    VALUES (:feed_id, :entry_key, CAST(:payload AS jsonb), :attempts, :last_error)
                    ON CONFLICT (feed_id, entry_key) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        attempts = pending_feed_entries.attempts + :attempts,
                        last_error = EXCLUDED.last_error
                """), {"feed_id": feed_id, "entry_key": key, "attempts": first_attempts,
                       "payload": json.dumps(payload, default=str),
                       "last_error": (error or "store failed")[:500]})
                queued += 1
            conn.commit()
        except Exception as exc:                                      # noqa: BLE001
            logger.error("could not queue %d pending entries for feed %s: %s",
                         len(failed_items), feed_id, describe_exception(exc))
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:                                         # noqa: BLE001
                pass
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:                                     # noqa: BLE001
                    pass
        return queued

    async def _replay_pending(self, feed_id: int, topic: str) -> List[Dict]:
        """Store the feed's queued entries. Rows that succeed are deleted;
        rows that fail again count another attempt and are dropped, with a
        log line, after ``PENDING_MAX_ATTEMPTS``. Returns the articles
        inserted this time, for enrichment."""
        conn = self.db._temp_get_connection()
        try:
            rows = conn.execute(text("""
                SELECT id, entry_key, payload, attempts
                  FROM pending_feed_entries WHERE feed_id = :feed_id ORDER BY id
                 LIMIT :budget
            """), {"feed_id": feed_id, "budget": NEW_ENTRIES_PER_POLL}).fetchall()
        finally:
            conn.close()
        if not rows:
            return []

        pending: List[Tuple[int, str, Dict, int]] = []
        for row in rows:
            row_id, key, payload, attempts = row[0], row[1], row[2], int(row[3] or 0)
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except ValueError:
                    payload = None
            if not isinstance(payload, dict):
                payload = {"url": key, "title": key}
            pending.append((row_id, key, payload, attempts))

        countries = await asyncio.to_thread(self._resolve_countries, [p[2] for p in pending])
        inserted: List[Dict] = []
        done_ids: List[int] = []
        retry: List[Tuple[int, int, str]] = []
        for row_id, key, payload, attempts in pending:
            outcome = await self._store_article(payload, topic, countries)
            if outcome == STORE_INSERTED:
                inserted.append(payload)
                done_ids.append(row_id)
            elif outcome == STORE_EXISTING:
                done_ids.append(row_id)
            else:
                attempts += 1
                if attempts >= PENDING_MAX_ATTEMPTS:
                    logger.error("giving up on pending entry %s for feed %s after %d attempts: %s",
                                 key, feed_id, attempts, self._last_store_error)
                    done_ids.append(row_id)
                else:
                    retry.append((row_id, attempts, self._last_store_error or "store failed"))

        conn = self.db._temp_get_connection()
        try:
            for row_id in done_ids:
                conn.execute(text("DELETE FROM pending_feed_entries WHERE id = :id"), {"id": row_id})
            for row_id, attempts, error in retry:
                conn.execute(text("""
                    UPDATE pending_feed_entries SET attempts = :attempts, last_error = :error WHERE id = :id
                """), {"id": row_id, "attempts": attempts, "error": error[:500]})
            conn.commit()
        finally:
            conn.close()
        if inserted or retry:
            logger.info("feed %s pending replay: %d stored, %d still queued",
                        feed_id, len(inserted), len(retry))
        return inserted

    def _resolve_countries(self, articles: List[Dict]) -> Dict[str, tuple]:
        """Publisher country and method per domain for one batch of articles.

        Returns ``{domain: (iso2 or None, method)}``, or an empty map if the
        registry is unavailable. Never fatal: an article we cannot place is
        still worth storing, so every failure here leaves the rows unstamped
        rather than stopping the feed.
        """
        try:
            from app.services.source_country import (
                countries_with_method, domain_for_article,
            )
        except Exception as e:                                    # noqa: BLE001
            logger.warning("source-country registry unavailable, RSS rows "
                           "will be stored unstamped: %s", e)
            return {}

        domains = []
        for art in articles:
            dom = domain_for_article(art.get('url'), art.get('source'))
            if dom and dom not in domains:
                domains.append(dom)
        if not domains:
            return {}
        try:
            return countries_with_method(self.db, domains)
        except Exception as e:                                    # noqa: BLE001
            logger.warning("source-country lookup failed for %s: %s", domains, e)
            return {}

    @staticmethod
    def _country_for(url: str, article: Dict, countries) -> tuple:
        """The (country, method) pair for one article, or (None, None)."""
        if not countries:
            return (None, None)
        try:
            from app.services.source_country import domain_for_article
            dom = domain_for_article(url, article.get('source'))
        except Exception:                                         # noqa: BLE001
            return (None, None)
        return countries.get(dom) or (None, None)


    async def _store_article(self, article: Dict, topic: str,
                             countries: Optional[Dict[str, tuple]] = None) -> str:
        """Store an article directly (no keyword association for RSS).

        Returns one of ``"inserted"``, ``"existing"`` or ``"failed"``. A
        duplicate is finished work; a failed insert is not, and the caller
        queues it (work package 16). The reason for a failure is left in
        ``self._last_store_error``.

        ``countries`` is the batch map from :meth:`_resolve_countries`; a
        domain missing from it stores a NULL country, which readers treat as
        "we could not place this publisher".
        """
        from sqlalchemy import insert as sql_insert
        from app.database_models import t_articles

        self._last_store_error = None
        url = (article.get('url') or '').strip()
        if not url:
            self._last_store_error = "entry has no URL"
            return STORE_FAILED

        conn = None
        try:
            # Which stored row this entry is, by identity rather than exact
            # URL (work package 4): a tracking variant of a known article is
            # that article. The lookups run off the event loop; they are
            # best-effort and fall back to the exact-URL check.
            item = dict(article, url=url, uri=url, topic=topic,
                        collector_source=article.get('collector_source') or 'rss')
            resolution = await asyncio.to_thread(self._resolve_identity, item)
            existing_uri = None
            if resolution is not None and resolution.existing and resolution.uri:
                existing_uri = resolution.uri
            elif self.db.facade.article_exists((url,)):
                existing_uri = url
            if existing_uri:
                if existing_uri != url:
                    logger.info("Same article as %s (by %s): %s", existing_uri,
                                getattr(resolution, 'matched_by', None), url)
                else:
                    logger.debug(f"RSS article already exists: {url}")
                # A repeat sighting still counts: fill what the row lacks and
                # record the observation and alias (work packages 4 and 8).
                await asyncio.to_thread(self._merge_and_observe, existing_uri, item, resolution)
                return STORE_EXISTING

            # English at insert, as every facade-based collector does. A
            # vendor's Turkish or German blog otherwise reaches the report
            # as written. Off the event loop: it can call a model.
            record = {'title': (article.get('title', '') or '')[:500],
                      'summary': (article.get('summary', '') or '')[:2000]}
            try:
                await self._english(record)
            except Exception as e:                            # noqa: BLE001
                logger.warning(f"Translation failed for {url}: {e}")

            now = datetime.now(timezone.utc)
            published = article.get('published_date') or None
            if published:
                provenance = article.get('date_provenance') or dates.PROV_FEED
                precision = article.get('publication_date_precision')
                if provenance == dates.PROV_WAYBACK:
                    # A first-capture date is an upper bound on the day.
                    precision = precision or dates.PREC_DAY
            else:
                # No date known: the row says so, and first_seen_at is the
                # discovery time. Never the current time as publication.
                published = None
                provenance = dates.PROV_UNKNOWN
                precision = None

            conn = self.db._temp_get_connection()
            country, method = self._country_for(url, article, countries)
            conn.execute(sql_insert(t_articles).values(
                uri=url,
                title=(record['title'] or '')[:500],
                original_title=record.get('original_title'),
                news_source=(article.get('source', 'RSS') or 'RSS')[:200],
                publication_date=published,
                published_at_raw=(article.get('published_at_raw') or None),
                publication_date_precision=precision,
                date_provenance=provenance,
                first_seen_at=now,
                last_seen_at=now,
                content_kind='excerpt',
                record_type='news',
                canonical_url=(getattr(resolution, 'canonical_url', None) or None),
                identity_method=(getattr(resolution, 'method', None) or None),
                summary=(record['summary'] or '')[:2000],
                original_summary=record.get('original_summary'),
                topic=topic,
                source_country=country,
                source_country_method=method,
                analyzed=False
            ))
            conn.commit()
            logger.debug(f"Stored RSS article: {url}")
            # The first observation and the URL alias for the new row.
            await asyncio.to_thread(self._observe, url, item, resolution)
            return STORE_INSERTED

        except Exception as e:
            self._last_store_error = describe_exception(e, host=host_of(url))
            logger.error(f"Error storing article {url}: {self._last_store_error}")
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:                                     # noqa: BLE001
                pass
            return STORE_FAILED
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # -- identity bookkeeping (work packages 4 and 8), all best-effort ------

    def _resolve_identity(self, item: Dict):
        """``article_identity.resolve_identity`` against the facade, or None
        when the service is unavailable. Never raises."""
        try:
            from app.services.article_identity import resolve_identity
            return resolve_identity(self.db.facade, item)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("identity resolution skipped for %s: %s", item.get('url'), exc)
            return None

    def _merge_and_observe(self, uri: str, item: Dict, resolution) -> None:
        """Fill what the stored row lacks from this sighting, then record
        the observation and alias. Mirrors ``create_article``'s repeat path."""
        try:
            from sqlalchemy import select, update
            from app.database_models import t_articles
            from app.services.article_identity import column_updates, merge_fields
            facade = self.db.facade
            row = facade._fetchone_with_rollback(
                select(t_articles.c.title, t_articles.c.news_source, t_articles.c.summary,
                       t_articles.c.publication_date, t_articles.c.content_kind,
                       t_articles.c.social_meta, t_articles.c.original_title,
                       t_articles.c.original_summary).where(t_articles.c.uri == uri),
                mappings=True)
            writes = column_updates(merge_fields(dict(row) if row else {}, item))
            if row and writes:
                facade._execute_with_rollback(
                    update(t_articles).where(t_articles.c.uri == uri).values(**writes))
                if set(writes) - {'last_seen_at'}:
                    logger.info("Merged %s into %s", sorted(set(writes) - {'last_seen_at'}), uri)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("merge skipped for %s: %s", uri, exc)
        self._observe(uri, item, resolution)

    def _observe(self, uri: str, item: Dict, resolution) -> None:
        try:
            from app.services.article_identity import record_observation
            record_observation(self.db.facade, uri, item, 'rss', resolution=resolution)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("observation skipped for %s: %s", uri, exc)

    @staticmethod
    async def _english(record: Dict) -> None:
        """Translate title and summary in place, off the event loop."""
        from app.utils.title_translation import english_fields
        await asyncio.to_thread(english_fields, record)

    async def _run_auto_ingest(
        self,
        articles: List[Dict],
        topic: str,
        relevance_threshold: int = None,
        default_factual_reporting: str = None
    ) -> int:
        """Run enrichment pipeline for RSS articles.

        RSS feeds always run enrichment - they have their own relevance threshold
        and are not tied to the keyword monitor's auto-ingest setting.

        Args:
            articles: List of article data from RSS feed
            topic: Topic name for context
            relevance_threshold: Per-feed relevance threshold (0=skip filtering, 1-100=threshold %)
            default_factual_reporting: Factual reporting level to set on articles ('very high', 'high', etc.)

        Returns:
            Number of articles successfully enriched
        """
        try:
            from app.services.automated_ingest_service import AutomatedIngestService

            # RSS feeds always enrich - they have their own relevance threshold setting
            # (not tied to keyword monitor's auto-ingest setting)
            logger.info(f"Running enrichment pipeline for RSS articles in topic '{topic}'")
            ingest_service = AutomatedIngestService(self.db)

            # Get keywords for the topic
            topic_keywords = self.db.facade.get_monitored_keywords_for_topic((topic,))

            # Format articles for batch processing
            batch_articles = []
            for article in articles:
                article_url = article.get('url', '').strip()
                if article_url:
                    batch_articles.append({
                        'uri': article_url,
                        'url': article_url,
                        'title': article.get('title', ''),
                        'news_source': article.get('source', 'RSS'),  # Use news_source key for pipeline compatibility
                        'published_date': article.get('published_date'),
                        'summary': article.get('summary', ''),
                        'topic': topic  # Include topic for pipeline consistency
                    })

            if batch_articles:
                # Convert relevance_threshold from percentage (0-100) to decimal (0.0-1.0)
                # 0 = skip filtering, otherwise convert to decimal
                threshold_override = None
                if relevance_threshold is not None:
                    if relevance_threshold == 0:
                        threshold_override = 0  # Signal to skip filtering
                    else:
                        threshold_override = relevance_threshold / 100.0  # Convert to 0.0-1.0 range

                result = await ingest_service.process_articles_batch(
                    articles=batch_articles,
                    topic=topic,
                    keywords=topic_keywords,
                    relevance_threshold_override=threshold_override,
                    route="rss",
                )
                saved = result.get('saved', 0)
                logger.info(f"Auto-ingest completed: {result}")

                # Apply default_factual_reporting to enriched articles if set
                if default_factual_reporting and saved > 0:
                    try:
                        from app.database_models import t_articles
                        article_uris = [a['uri'] for a in batch_articles if a.get('uri')]
                        if article_uris:
                            update_factual_stmt = update(t_articles).where(
                                t_articles.c.uri.in_(article_uris)
                            ).values(
                                factual_reporting=default_factual_reporting
                            )
                            conn = self.db._temp_get_connection()
                            try:
                                conn.execute(update_factual_stmt)
                                conn.commit()
                                logger.info(f"Set factual_reporting='{default_factual_reporting}' for {len(article_uris)} RSS articles")
                            finally:
                                conn.close()
                    except Exception as fr_err:
                        logger.error(f"Failed to set factual_reporting on RSS articles: {fr_err}")

                # Create completion notification
                try:
                    self.db.facade.create_notification(
                        username=None,  # System-wide notification
                        type='auto_ingest_complete',
                        title='RSS Feed Complete',
                        message=f'Scheduled fetch: {len(articles)} articles, {saved} enriched',
                        link='/gather'
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to create RSS notification: {notif_err}")

                return saved

        except Exception as e:
            logger.error(f"Auto-ingest pipeline error: {e}")

        return 0

    def _update_monitor_status(
        self,
        is_running: Optional[bool] = None,
        last_check_time: Optional[datetime] = None,
        feeds_checked: Optional[int] = None,
        articles_fetched: Optional[int] = None,
        last_error: Optional[str] = None
    ):
        """Update the monitor status in database."""
        global _monitor_status

        try:
            updates = []
            params = {"id": 1}

            if is_running is not None:
                updates.append("is_running = :running")
                params["running"] = is_running
                _monitor_status["running"] = is_running

            if last_check_time is not None:
                updates.append("last_check_time = :last_check")
                params["last_check"] = last_check_time
                _monitor_status["last_check_time"] = last_check_time

            if feeds_checked is not None:
                updates.append("feeds_checked = :feeds")
                params["feeds"] = feeds_checked
                _monitor_status["feeds_checked"] = feeds_checked

            if articles_fetched is not None:
                updates.append("articles_fetched = :articles")
                params["articles"] = articles_fetched
                _monitor_status["articles_fetched"] = articles_fetched

            if last_error is not None:
                updates.append("last_error = :error")
                params["error"] = last_error[:500] if last_error else None
                _monitor_status["last_error"] = last_error
            elif last_error == "":
                updates.append("last_error = NULL")
                _monitor_status["last_error"] = None

            updates.append("updated_at = NOW()")

            if updates:
                conn = self.db._temp_get_connection()
                try:
                    conn.execute(text(f"""
                        UPDATE rss_feed_monitor_status
                        SET {', '.join(updates)}
                        WHERE id = :id
                    """), params)
                    conn.commit()
                finally:
                    conn.close()

        except Exception as e:
            logger.error(f"Error updating monitor status: {e}")

    async def run_check_cycle(self):
        """Run one check cycle - fetch all due feeds."""
        try:
            self._update_monitor_status(is_running=True)

            due_feeds = await self.get_due_feeds()

            if not due_feeds:
                self._update_monitor_status(
                    is_running=False,
                    last_check_time=datetime.now(timezone.utc)
                )
                return

            logger.info(f"Found {len(due_feeds)} RSS feeds due for checking")

            total_articles = 0
            for feed in due_feeds:
                try:
                    count = await self.fetch_feed(feed)
                    total_articles += count
                except Exception as e:
                    logger.error(f"Error processing feed {feed['id']}: {e}")

            self._update_monitor_status(
                is_running=False,
                last_check_time=datetime.now(timezone.utc),
                feeds_checked=len(due_feeds),
                articles_fetched=total_articles,
                last_error=""
            )

            logger.info(f"RSS feed check cycle complete: {len(due_feeds)} feeds, {total_articles} articles")

        except Exception as e:
            logger.error(f"Error in RSS feed check cycle: {e}")
            self._update_monitor_status(
                is_running=False,
                last_error=str(e)
            )


async def run_rss_feed_monitor():
    """Main entry point for the RSS feed monitor background task."""
    logger.info("Starting RSS feed monitor background task")

    try:
        db = get_database_instance()
        monitor = RSSFeedMonitor(db)

        while True:
            try:
                await monitor.run_check_cycle()
            except Exception as e:
                logger.error(f"Error in RSS feed monitor cycle: {e}")

            # Wait before next check (every minute)
            await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Fatal error in RSS feed monitor: {e}")
        raise
