"""
Monitor and execute scheduled brand watcher classification.
Follows the same pattern as policy_tracker_monitor.py.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional, Any, List
from sqlalchemy import text

from app.database import Database, get_database_instance

logger = logging.getLogger(__name__)

# Global variable to track task status
_background_task_status = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "schedules_checked": 0,
    "schedules_run": 0,
    "is_checking": False
}


def get_task_status() -> Dict:
    """Get the current status of the brand watcher monitor background task."""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    schedule_interval: Optional[int],
    schedule_unit: Optional[str],
    schedule_time: Optional[Any],
    from_time: Optional[datetime] = None
) -> datetime:
    """Calculate the next run time based on schedule configuration."""
    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        hour, minute = 0, 0
        if isinstance(schedule_time, dt_time):
            hour, minute = schedule_time.hour, schedule_time.minute
        elif isinstance(schedule_time, timedelta):
            total_seconds = int(schedule_time.total_seconds())
            hour = total_seconds // 3600
            minute = (total_seconds % 3600) // 60
        elif isinstance(schedule_time, str):
            try:
                parts = schedule_time.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Could not parse schedule_time string: {schedule_time}")
                hour, minute = 9, 0

        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule_type == 'interval' and schedule_interval and schedule_unit:
        if schedule_unit == 'minutes':
            delta = timedelta(minutes=schedule_interval)
        elif schedule_unit == 'hours':
            delta = timedelta(hours=schedule_interval)
        elif schedule_unit == 'days':
            delta = timedelta(days=schedule_interval)
        else:
            delta = timedelta(hours=schedule_interval)
        return now + delta

    return now + timedelta(hours=24)


class BrandWatcherMonitor:
    """Monitor for scheduled brand watcher classification."""

    def __init__(self, db: Database):
        self.db = db
        self.running_schedules: set = set()

    def get_due_schedules(self) -> List[Dict]:
        """Get all schedules that are due to run (next_run_at <= NOW())."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, brand_id, run_type, days_back, topics,
                       schedule_type, schedule_interval, schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count,
                       notify_on_complete, notify_threshold
                FROM bw_tracker_schedules
                WHERE schedule_enabled = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            schedules = [dict(row._mapping) for row in result]
            conn.close()
            return schedules
        except Exception as e:
            logger.error(f"Error getting due brand watcher schedules: {e}")
            return []

    def update_schedule_status(
        self,
        schedule_id: int,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[datetime] = None,
        articles_processed: int = 0,
        articles_categorized: int = 0
    ) -> None:
        """Update a schedule's run status and next run time."""
        try:
            conn = self.db._temp_get_connection()

            updates = ["last_run_at = NOW()", "last_run_status = :status"]
            params = {"id": schedule_id, "status": status}

            if error:
                updates.append("last_run_error = :error")
                params["error"] = error
            else:
                updates.append("last_run_error = NULL")

            if next_run_at:
                updates.append("next_run_at = :next_run")
                params["next_run"] = next_run_at

            updates.append("last_run_articles_processed = :articles_processed")
            params["articles_processed"] = articles_processed

            updates.append("last_run_articles_categorized = :articles_categorized")
            params["articles_categorized"] = articles_categorized

            if status == 'success':
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            conn.execute(text(f"""
                UPDATE bw_tracker_schedules
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating brand watcher schedule status: {e}")

    async def run_schedule(self, schedule: Dict) -> Dict[str, Any]:
        """Execute a single schedule's classification."""
        schedule_id = schedule['id']
        schedule_name = schedule['name']

        result = {
            "success": False,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "articles_processed": 0,
            "articles_categorized": 0,
            "error": None
        }

        if schedule_id in self.running_schedules:
            logger.info(f"Brand watcher schedule {schedule_name} is already running, skipping")
            return result

        self.running_schedules.add(schedule_id)
        self.update_schedule_status(schedule_id, 'running')

        try:
            from app.routes.brand_watcher_routes import _run_classification_task
            from app.database import get_database_instance

            db = get_database_instance()
            conn = db._temp_get_connection()

            brand_id = schedule.get('brand_id')
            run_type = schedule.get('run_type', 'incremental')
            days_back = schedule.get('days_back', 30)

            # Parse topics from JSONB column
            raw_topics = schedule.get('topics')
            if isinstance(raw_topics, str):
                try:
                    topics = json.loads(raw_topics)
                except (json.JSONDecodeError, TypeError):
                    topics = None
            elif isinstance(raw_topics, list):
                topics = raw_topics
            else:
                topics = None

            logger.info(f"Running brand watcher schedule: {schedule_name} (ID: {schedule_id}, brand_id: {brand_id}, topics: {topics})")

            # Create a run record
            run_result = conn.execute(text("""
                INSERT INTO bw_tracker_runs (brand_id, run_type, status)
                VALUES (:brand_id, :run_type, 'running')
                RETURNING id
            """), {"brand_id": brand_id, "run_type": run_type})
            run_id = run_result.fetchone()[0]
            conn.commit()
            conn.close()

            # Run classification
            await _run_classification_task(run_id, brand_id, run_type, days_back, topics)

            # Get the results
            conn = db._temp_get_connection()
            run_info = conn.execute(text("""
                SELECT articles_processed, articles_categorized
                FROM bw_tracker_runs
                WHERE id = :id
            """), {"id": run_id}).fetchone()
            conn.close()

            if run_info:
                result["articles_processed"] = run_info[0] or 0
                result["articles_categorized"] = run_info[1] or 0

            result["success"] = True

            # Calculate next run time
            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval'),
                schedule_unit=schedule.get('schedule_unit'),
                schedule_time=schedule.get('schedule_time')
            )

            self.update_schedule_status(
                schedule_id,
                'success',
                next_run_at=next_run,
                articles_processed=result["articles_processed"],
                articles_categorized=result["articles_categorized"]
            )

            # Send notification if configured
            if schedule.get('notify_on_complete') and result["articles_categorized"] >= schedule.get('notify_threshold', 10):
                await self._send_notification(schedule, result)

            # Check for category spikes
            await self._check_category_spikes(brand_id, schedule_name)

            logger.info(
                f"Brand watcher schedule {schedule_name} completed. "
                f"Processed: {result['articles_processed']}, Categorized: {result['articles_categorized']}. "
                f"Next run: {next_run}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running brand watcher schedule {schedule_name}: {error_msg}", exc_info=True)
            result["error"] = error_msg

            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval'),
                schedule_unit=schedule.get('schedule_unit'),
                schedule_time=schedule.get('schedule_time')
            )
            self.update_schedule_status(schedule_id, 'error', error=error_msg, next_run_at=next_run)

        finally:
            self.running_schedules.discard(schedule_id)

        return result

    async def _send_notification(self, schedule: Dict, stats: Dict) -> None:
        """Send notification about completed classification."""
        try:
            db = get_database_instance()
            brand_name = schedule.get('name', 'Brand Watcher')

            title = f"Brand Watcher: {brand_name}"
            message = (
                f"Classified {stats['articles_categorized']} articles.\n"
                f"Total processed: {stats['articles_processed']}"
            )

            db.facade.create_notification(
                username=None,
                type='brand_watcher',
                title=title,
                message=message,
                link='/newsfeed?tab=brand-watcher'
            )
            logger.info(f"Notification created for brand watcher schedule {schedule.get('name')}")
        except Exception as e:
            logger.error(f"Failed to send notification for brand watcher schedule: {e}")

    async def _check_category_spikes(self, brand_id: Optional[int], schedule_name: str) -> None:
        """Check for category spikes after classification and create alerts."""
        try:
            db = get_database_instance()
            conn = db._temp_get_connection()

            brand_filter = "AND bac.brand_id = :brand_id" if brand_id else ""
            params = {}
            if brand_id:
                params["brand_id"] = brand_id

            # Get category counts for last 7 days
            recent_result = conn.execute(text(f"""
                SELECT bac.category, COUNT(DISTINCT bac.article_uri) as cnt
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE a.publication_date >= (NOW() - INTERVAL '7 days')::text
                {brand_filter}
                GROUP BY bac.category
            """), params)
            recent_counts = {row[0]: row[1] for row in recent_result.fetchall()}

            # Get 30-day rolling average (per week)
            avg_result = conn.execute(text(f"""
                SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE a.publication_date >= (NOW() - INTERVAL '30 days')::text
                  AND a.publication_date < (NOW() - INTERVAL '7 days')::text
                {brand_filter}
                GROUP BY bac.category
            """), params)
            avg_counts = {row[0]: float(row[1]) for row in avg_result.fetchall()}

            conn.close()

            # Check for spikes (2x average)
            for category, count in recent_counts.items():
                avg = avg_counts.get(category, 0)
                if avg > 0 and count >= avg * 2 and count >= 5:
                    # Get brand name for notification
                    brand_display = schedule_name
                    if brand_id:
                        try:
                            conn2 = db._temp_get_connection()
                            br = conn2.execute(text(
                                "SELECT display_name FROM bw_brands WHERE id = :id"
                            ), {"id": brand_id}).fetchone()
                            conn2.close()
                            if br:
                                brand_display = br[0]
                        except Exception:
                            pass

                    db.facade.create_notification(
                        username=None,
                        type='brand_watcher_alert',
                        title=f'Spike: {category} for {brand_display}',
                        message=f'{count} articles this week (avg: {avg:.0f}/week)',
                        link='/newsfeed?tab=brand-watcher'
                    )
                    logger.info(f"Spike alert: {category} for {brand_display} - {count} articles (avg: {avg:.0f})")

        except Exception as e:
            logger.error(f"Error checking category spikes: {e}")


def _check_auto_retrain(db: Database) -> None:
    """Check if the SLM classifier should be retrained.

    Runs weekly: if 500+ new classified articles since last training,
    triggers a background retrain.
    """
    import os
    import subprocess

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    marker_file = os.path.join(base_dir, "models", "brand_watcher_classifier", ".last_train_timestamp")

    # Check marker
    last_train = datetime.min
    if os.path.exists(marker_file):
        try:
            with open(marker_file, 'r') as f:
                last_train = datetime.fromisoformat(f.read().strip())
        except Exception:
            pass

    # Only check weekly
    if (datetime.now() - last_train).days < 7:
        return

    try:
        conn = db._temp_get_connection()
        count = conn.execute(text("""
            SELECT COUNT(*) FROM bw_article_categories
            WHERE classified_at > :since
        """), {"since": last_train}).scalar() or 0
        conn.close()

        if count < 500:
            logger.debug(f"Auto-retrain check: only {count} new classifications since last train, skipping")
            return

        logger.info(f"Auto-retrain triggered: {count} new classifications since last train at {last_train}")

        # Run training script in background
        train_script = os.path.join(base_dir, "scripts", "train_brand_watcher_classifier.py")
        if os.path.exists(train_script):
            subprocess.Popen(
                ["python", train_script],
                cwd=base_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Update marker
            os.makedirs(os.path.dirname(marker_file), exist_ok=True)
            with open(marker_file, 'w') as f:
                f.write(datetime.now().isoformat())

            db.facade.create_notification(
                username=None,
                type='brand_watcher',
                title='Brand Watcher: SLM Retrain Started',
                message=f'Auto-retrain triggered with {count} new classified articles.',
                link='/newsfeed?tab=brand-watcher'
            )
        else:
            logger.warning(f"Training script not found: {train_script}")

    except Exception as e:
        logger.error(f"Auto-retrain check error: {e}")



# ---------------------------------------------------------------------------
# Adverse-media alert evaluation (push alerting)
# ---------------------------------------------------------------------------

# Default rule thresholds; overridable per-rule via bw_alert_config.rules JSONB,
# e.g. {"neg_social_spike": {"enabled": true, "min_posts": 4}, ...}
# "min_new": articles/posts not covered by any previous alert of the rule —
# identity-keyed dedup means a rule only re-fires on that much NEW content.
_ADVERSE_RULE_DEFAULTS = {
    "neg_social_spike":    {"enabled": True, "min_prior": 2, "multiplier": 2.0, "min_new": 2},
    "high_reach_negative": {"enabled": True, "min_engagement": 50, "window_hours": 24, "min_new": 1},
    "news_net_negative":   {"enabled": True, "net_threshold": -20, "min_scored": 5, "window_days": 7,
                            "refire_worsen_points": 10},
    "category_spike":      {"enabled": True, "multiplier": 2.0, "min_count": 5, "min_new": 3},
    "high_risk_finding":   {"enabled": True, "window_hours": 24, "min_new": 1},
    "neg_consensus_story": {"enabled": True, "min_scored": 3, "neg_share": 0.7, "window_hours": 48},
    "new_critic":          {"enabled": True, "recent_hours": 48, "min_recent_neg": 2,
                            "min_engagement_single": 50, "lookback_days": 30},
    "coordinated_negative": {"enabled": True, "window_hours": 72, "min_authors": 3},
    "glassdoor_deterioration": {"enabled": True, "rating_drop": 0.2, "outlook_drop": 0.10,
                                "lookback_days": 35, "min_span_days": 7},
    "signals_flag":            {"enabled": True, "recent_days": 7},
}

_NEG_SENT_SQL = "(sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR sentiment ILIKE '%pessimis%' OR sentiment ILIKE '%critical%' OR sentiment ILIKE '%alarm%')"
_POS_SENT_SQL = "(sentiment ILIKE '%positiv%' OR sentiment ILIKE '%optimis%')"
from app.services.social_sources import social_src_sql as _social_src_sql
_SOCIAL_SRC_SQL = _social_src_sql("news_source")
_ENGAGEMENT_SQL = ("(COALESCE((social_meta->>'likes')::float,0) + 2*COALESCE((social_meta->>'reposts')::float,0)"
                   " + COALESCE((social_meta->>'comments')::float,0) + COALESCE((social_meta->>'plays')::float,0)/100)")


def _not_fp_sql(alias: str = "articles") -> str:
    """Exclude items a human flagged as false positives (bw_finding_reviews).

    A flag under ANY brand removes the item from alert counts everywhere —
    the same spam post routinely trips several brands' keywords at once.
    """
    return (f"NOT EXISTS (SELECT 1 FROM bw_finding_reviews _fpr"
            f" WHERE _fpr.article_uri = {alias}.uri AND _fpr.status = 'false_positive')")


def _dedup_exists(conn, dedup_key) -> bool:
    """True when an event with this dedup_key already fired.

    Checked BEFORE composing bodies that cost an LLM call — the rule condition
    stays true for days, and evaluation re-runs every ~15 minutes.
    """
    from sqlalchemy import text as _text
    return conn.execute(_text("SELECT 1 FROM bw_alert_events WHERE dedup_key = :k"),
                        {"k": dedup_key}).fetchone() is not None


def _uris_sig(uris) -> str:
    """Stable short signature over a set of article URIs, for identity dedup keys."""
    import hashlib
    return hashlib.sha1("|".join(sorted(uris)).encode("utf-8", "ignore")).hexdigest()[:16]


def _alerted_uris(conn, brand_id, rule, days: int = 30, key_prefix: str = None) -> set:
    """URIs this rule already alerted on for the brand.

    The ledger is the ``alert_uris`` list each identity-keyed event stores in
    its payload — an article counted into one alert never counts as "new"
    again (within the lookback). ``key_prefix`` narrows the ledger to a
    sub-scope (e.g. one category / risk type) via the dedup_key format.
    """
    from sqlalchemy import text as _text
    q = ("SELECT DISTINCT jsonb_array_elements_text(payload->'alert_uris') "
         "FROM bw_alert_events WHERE rule = :r AND brand_id = :b "
         "AND payload->'alert_uris' IS NOT NULL "
         "AND created_at >= now() - (:d || ' days')::interval")
    params = {"r": rule, "b": brand_id, "d": str(days)}
    if key_prefix:
        q += " AND dedup_key LIKE :pfx"
        params["pfx"] = key_prefix.replace("%", "").replace("_", r"\_") + "%"
    return {r[0] for r in conn.execute(_text(q), params).fetchall()}


def _fired_recently(conn, brand_id, rule, hours, key_prefix: str = None) -> bool:
    """Rate floor: the rule already fired for this brand within the cooldown.

    Identity-keyed alerts only fire on NEW content, but a stream of trickling
    articles must not produce an alert every 15-minute cycle — the cooldown
    caps each rule (or sub-scope via ``key_prefix``) at one alert per window;
    content that arrives during the window alerts after it expires.
    """
    from sqlalchemy import text as _text
    q = ("SELECT 1 FROM bw_alert_events WHERE rule = :r AND brand_id = :b "
         "AND created_at >= now() - (:h || ' hours')::interval")
    params = {"r": rule, "b": brand_id, "h": str(hours)}
    if key_prefix:
        q += " AND dedup_key LIKE :pfx"
        params["pfx"] = key_prefix.replace("%", "").replace("_", r"\_") + "%"
    return conn.execute(_text(q), params).fetchone() is not None


def _insert_alert_event(conn, brand_id, rule, severity, title, body, payload, dedup_key) -> bool:
    """Insert an alert event; dedup_key uniqueness makes re-evaluation idempotent."""
    from sqlalchemy import text as _text
    import json as _json
    r = conn.execute(_text("""
        INSERT INTO bw_alert_events (brand_id, rule, severity, title, body, payload, dedup_key)
        VALUES (:b, :r, :sev, :t, :body, :p, :k)
        ON CONFLICT (dedup_key) DO NOTHING
        RETURNING id
    """), {"b": brand_id, "r": rule, "sev": severity, "t": title, "body": body,
           "p": _json.dumps(payload or {}), "k": dedup_key})
    return r.fetchone() is not None


def evaluate_adverse_alerts(db) -> int:
    """Evaluate adverse-media rules per enabled brand; persist + deliver new events.

    Server-side mirror of the dashboard's client-side "Problems" rules, so alerts
    fire unattended. Returns the number of NEW events created.
    """
    from sqlalchemy import text as _text
    from app.services.brand_alert_service import (
        get_alert_config, deliver_pending_events,
        fetch_negative_social_posts, narrate_social_posts, social_posts_md,
    )

    def _social_body(lead: str, bname_, posts) -> str:
        """Alert body = the count sentence + what the posts actually say + linked posts.

        A bare count is not actionable — the reader needs the substance and a way
        to click through to the posts themselves.
        """
        body = lead
        narration = narrate_social_posts(bname_, posts)
        if narration:
            body += f"\n\n**What the posts say:** {narration}"
        if posts:
            body += "\n\n" + "\n".join(social_posts_md(posts))
        return body

    def _posts_payload(posts) -> list:
        return [{k: p.get(k) for k in ("title", "url", "source", "author", "engagement")}
                for p in posts[:5]]

    conn = db._temp_get_connection()
    created = 0
    try:
        cfg = get_alert_config(conn)
        if not cfg or not cfg.get("enabled"):
            return 0
        rules_cfg = cfg.get("rules") or {}
        # No more rolling time bucket in dedup keys: alerts are keyed on the
        # IDENTITY of what fired them (story, author, article set, snapshot
        # pair), so a still-true window condition can't re-alert on the same
        # content. cooldown_hours survives as a per-rule rate floor only.
        cooldown_h = cfg.get("cooldown_hours") or 24

        def rule(name):
            merged = dict(_ADVERSE_RULE_DEFAULTS.get(name, {}))
            merged.update(rules_cfg.get(name) or {})
            return merged

        brands = conn.execute(_text(
            "SELECT id, display_name, name, brand_keywords FROM bw_brands WHERE enabled = true")).fetchall()
        import json as _json
        import re as _re
        for bid, bname, bslug, bkw in brands:
            # Own-brand handle tokens (mirror of the dashboard's isOwn): @wileyhealth
            # posting positively/negatively about Wiley is the brand, not a third party.
            _kw = bkw if isinstance(bkw, list) else (_json.loads(bkw) if bkw else [])
            own_tokens = {_re.sub(r'[^a-z0-9]', '', str(t).lower()) for t in [bslug, *_kw]}
            own_tokens = {t for t in own_tokens if len(t) >= 3}
            def _is_own_handle(handle):
                lead = _re.sub(r'[^a-z0-9]', '', (handle or '').split('.')[0].lower())
                return bool(lead) and any(lead.startswith(t) for t in own_tokens)
            topic = f"Brand Monitoring {bname}"

            # 1) Negative-social spike: last 48h vs prior 48h.
            rc = rule("neg_social_spike")
            if rc.get("enabled"):
                row = conn.execute(_text(f"""
                    SELECT
                      COUNT(*) FILTER (WHERE publication_date >= to_char(now() - interval '48 hours','YYYY-MM-DD"T"HH24:MI:SS')) AS recent,
                      COUNT(*) FILTER (WHERE publication_date <  to_char(now() - interval '48 hours','YYYY-MM-DD"T"HH24:MI:SS')
                                         AND publication_date >= to_char(now() - interval '96 hours','YYYY-MM-DD"T"HH24:MI:SS')) AS prior
                    FROM articles
                    WHERE topic = :t AND {_SOCIAL_SRC_SQL} AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
                      AND {_not_fp_sql()}
                """), {"t": topic}).fetchone()
                recent, prior = row[0] or 0, row[1] or 0
                if (prior >= rc["min_prior"] and recent >= prior * rc["multiplier"]
                        and not _fired_recently(conn, bid, "neg_social_spike", cooldown_h)):
                    uris = [r[0] for r in conn.execute(_text(f"""
                        SELECT uri FROM articles
                        WHERE topic = :t AND {_SOCIAL_SRC_SQL} AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
                          AND publication_date >= to_char(now() - interval '48 hours','YYYY-MM-DD"T"HH24:MI:SS')
                          AND {_not_fp_sql()}
                    """), {"t": topic}).fetchall()]
                    new_set = set(uris) - _alerted_uris(conn, bid, "neg_social_spike")
                    if len(new_set) >= int(rc.get("min_new", 2)):
                        posts = fetch_negative_social_posts(conn, topic, 48, limit=20)
                        posts = [p for p in posts if p.get("url") in new_set][:6] or posts[:6]
                        if _insert_alert_event(conn, bid, "neg_social_spike", "high",
                                f"{bname}: negative social posts doubled ({recent} in 48h vs {prior} prior)",
                                _social_body(
                                    f"Negative on-brand social posts for {bname} jumped from {prior} to {recent} in the last 48 hours"
                                    f" ({len(new_set)} not previously alerted).",
                                    bname, posts),
                                {"recent": recent, "prior": prior, "new_posts": len(new_set),
                                 "posts": _posts_payload(posts), "alert_uris": uris[:300]},
                                f"neg_social_spike|{bid}|{_uris_sig(new_set)}"):
                            created += 1

            # 2) High-reach negative post in the last window. Keyed on the set
            #    of not-yet-alerted posts — each post alerts once, ever.
            rc = rule("high_reach_negative")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    SELECT uri, {_ENGAGEMENT_SQL}
                    FROM articles
                    WHERE topic = :t AND {_SOCIAL_SRC_SQL} AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
                      AND publication_date >= to_char(now() - (:wh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')
                      AND {_ENGAGEMENT_SQL} >= :minEng
                      AND {_not_fp_sql()}
                """), {"t": topic, "wh": str(rc["window_hours"]), "minEng": rc["min_engagement"]}).fetchall()
                if rows and not _fired_recently(conn, bid, "high_reach_negative", cooldown_h):
                    ledger = _alerted_uris(conn, bid, "high_reach_negative")
                    new_rows = [(u, e) for u, e in rows if u not in ledger]
                    n = len(new_rows)
                    if n >= int(rc.get("min_new", 1)):
                        new_set = {u for u, _e in new_rows}
                        max_eng = max((e or 0) for _u, e in new_rows)
                        posts = fetch_negative_social_posts(
                            conn, topic, int(rc["window_hours"]),
                            min_engagement=rc["min_engagement"], limit=20)
                        posts = [p for p in posts if p.get("url") in new_set][:6] or posts[:6]
                        if _insert_alert_event(conn, bid, "high_reach_negative", "high",
                                f"{bname}: {n} high-reach negative post{'s' if n != 1 else ''} circulating",
                                _social_body(
                                    f"{n} new negative post{'s' if n != 1 else ''} about {bname} with engagement >= {rc['min_engagement']} "
                                    f"(max {int(max_eng)}) in the last {rc['window_hours']}h.",
                                    bname, posts),
                                {"count": n, "max_engagement": max_eng, "posts": _posts_payload(posts),
                                 "alert_uris": [u for u, _e in rows][:300]},
                                f"high_reach_negative|{bid}|{_uris_sig(new_set)}"):
                            created += 1

            # 3) News net-negative over the window.
            rc = rule("news_net_negative")
            if rc.get("enabled"):
                row = conn.execute(_text(f"""
                    SELECT
                      COUNT(*) FILTER (WHERE {_POS_SENT_SQL}) AS pos,
                      COUNT(*) FILTER (WHERE {_NEG_SENT_SQL}) AS neg,
                      COUNT(*) FILTER (WHERE sentiment IS NOT NULL AND sentiment <> '') AS scored
                    FROM articles a
                    JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
                    WHERE a.publication_date >= to_char(now() - (:wd || ' days')::interval,'YYYY-MM-DD')
                      AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                      AND {_not_fp_sql('a')}
                """), {"b": bid, "wd": str(rc["window_days"])}).fetchone()
                pos, neg, scored = row[0] or 0, row[1] or 0, row[2] or 0
                if scored >= rc["min_scored"]:
                    net = round(((pos - neg) / scored) * 100)
                    if net <= rc["net_threshold"]:
                        # State alert, not an event: fire on ENTERING the bad
                        # state, then only when it materially worsens vs the
                        # last alert. Periodic "still negative" reminders are
                        # the digest's job.
                        prev = conn.execute(_text("""
                            SELECT payload->>'net' FROM bw_alert_events
                            WHERE rule = 'news_net_negative' AND brand_id = :b
                            ORDER BY created_at DESC LIMIT 1
                        """), {"b": bid}).fetchone()
                        prev_net = None
                        if prev and prev[0] is not None:
                            try:
                                prev_net = int(float(prev[0]))
                            except ValueError:
                                prev_net = None
                        worsen_by = int(rc.get("refire_worsen_points", 10))
                        if prev_net is None or net <= prev_net - worsen_by:
                            if _insert_alert_event(conn, bid, "news_net_negative", "high",
                                    f"{bname}: news sentiment net-negative ({net})",
                                    f"News coverage of {bname} over the last {rc['window_days']} days is net {net} "
                                    f"({pos} positive / {neg} negative of {scored} scored)"
                                    + (f" — down from {prev_net} at the last alert." if prev_net is not None else "."),
                                    {"net": net, "pos": pos, "neg": neg, "scored": scored},
                                    f"news_net_negative|{bid}|{net}"):
                                created += 1

            # 4) Category spike: this week vs 30d weekly average.
            rc = rule("category_spike")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    WITH weekly AS (
                      SELECT bac.category,
                        COUNT(*) FILTER (WHERE a.publication_date >= to_char(now() - interval '7 days','YYYY-MM-DD')) AS cur,
                        COUNT(*) FILTER (WHERE a.publication_date >= to_char(now() - interval '30 days','YYYY-MM-DD')) / 4.0 AS avg
                      FROM bw_article_categories bac
                      JOIN articles a ON a.uri = bac.article_uri
                      WHERE bac.brand_id = :b
                        AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                        AND {_not_fp_sql('a')}
                      GROUP BY bac.category)
                    SELECT category, cur, avg FROM weekly
                    WHERE cur >= :minc AND avg > 0 AND cur >= avg * :mult
                """), {"b": bid, "minc": rc["min_count"], "mult": rc["multiplier"]}).fetchall()
                for cat, cur, avg in rows:
                    if _fired_recently(conn, bid, "category_spike", cooldown_h,
                                       key_prefix=f"category_spike|{bid}|{cat}|"):
                        continue
                    uris = [r[0] for r in conn.execute(_text(f"""
                        SELECT a.uri
                        FROM bw_article_categories bac
                        JOIN articles a ON a.uri = bac.article_uri
                        WHERE bac.brand_id = :b AND bac.category = :c
                          AND a.publication_date >= to_char(now() - interval '7 days','YYYY-MM-DD')
                          AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                          AND {_not_fp_sql('a')}
                    """), {"b": bid, "c": cat}).fetchall()]
                    new_set = set(uris) - _alerted_uris(
                        conn, bid, "category_spike", key_prefix=f"category_spike|{bid}|{cat}|")
                    if len(new_set) < int(rc.get("min_new", 3)):
                        continue
                    if _insert_alert_event(conn, bid, "category_spike", "medium",
                            f"{bname}: '{cat}' coverage spike ({cur} this week, avg {avg:.1f})",
                            f"Category '{cat}' for {bname} has {cur} articles this week vs a 30-day weekly average of {avg:.1f} "
                            f"({len(new_set)} not previously alerted).",
                            {"category": cat, "current": cur, "average": float(avg),
                             "new_articles": len(new_set), "alert_uris": uris[:300]},
                            f"category_spike|{bid}|{cat}|{_uris_sig(new_set)}"):
                        created += 1

            # 5) New high-severity adverse-risk finding (bw_article_risks).
            rc = rule("high_risk_finding")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    SELECT r.risk_type, COUNT(*), MAX(a.title), array_agg(DISTINCT a.uri)
                    FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
                    WHERE r.brand_id = :b AND r.severity = 'high'
                      AND r.detected_at >= now() - (:wh || ' hours')::interval
                      AND {_not_fp_sql('a')}
                    GROUP BY r.risk_type
                """), {"b": bid, "wh": str(rc["window_hours"])}).fetchall()
                for risk_type, n, sample_title, uris in rows:
                    new_set = set(uris or []) - _alerted_uris(
                        conn, bid, "high_risk_finding", key_prefix=f"high_risk_finding|{bid}|{risk_type}|")
                    if len(new_set) < int(rc.get("min_new", 1)):
                        continue
                    if _insert_alert_event(conn, bid, "high_risk_finding", "high",
                            f"{bname}: high-severity {risk_type.replace('_', '/')} finding",
                            f"{len(new_set)} new article{'s' if len(new_set) != 1 else ''} flagged {risk_type} (high severity) for {bname} "
                            f"in the last {rc['window_hours']}h. e.g. \"{(sample_title or '')[:120]}\"",
                            {"risk_type": risk_type, "count": n, "new_articles": len(new_set),
                             "alert_uris": list(uris or [])[:300]},
                            f"high_risk_finding|{bid}|{risk_type}|{_uris_sig(new_set)}"):
                        created += 1

            # 6) Negative-consensus story: a story whose syndicated copies are
            #    predominantly negative — the framing is consensus, not one outlet.
            rc = rule("neg_consensus_story")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    SELECT st.story_group_id,
                           COUNT(*) FILTER (WHERE COALESCE(a.sentiment,'') <> '') AS scored,
                           COUNT(*) FILTER (WHERE a.sentiment ILIKE '%negativ%' OR a.sentiment ILIKE '%concern%'
                                              OR a.sentiment ILIKE '%pessimis%' OR a.sentiment ILIKE '%critical%'
                                              OR a.sentiment ILIKE '%alarm%') AS neg,
                           MAX(a.title) AS sample_title
                    FROM bw_article_stories st
                    JOIN articles a ON a.uri = st.article_uri
                    WHERE st.brand_id = :b
                      AND a.publication_date >= to_char(now() - (:wh || ' hours')::interval,'YYYY-MM-DD')
                      AND {_not_fp_sql('a')}
                    GROUP BY st.story_group_id
                """), {"b": bid, "wh": str(rc["window_hours"])}).fetchall()
                for group_id, scored, neg, sample_title in rows:
                    if (scored or 0) >= rc["min_scored"] and (neg or 0) / scored >= rc["neg_share"]:
                        if _insert_alert_event(conn, bid, "neg_consensus_story", "high",
                                f"{bname}: negative consensus across {neg} of {scored} sources",
                                f"A story about {bname} is framed negatively by {neg} of {scored} scored sources "
                                f"in the last {rc['window_hours']}h — consensus framing, not a single outlet's take. "
                                f"\"{(sample_title or '')[:120]}\"",
                                {"story_group_id": group_id, "scored": scored, "neg": neg},
                                f"neg_consensus_story|{bid}|{group_id}"):
                            created += 1

            # 7) New critic emerged: an account whose FIRST negative on-brand post(s)
            #    appeared in the recent window (no negatives in the prior lookback).
            rc = rule("new_critic")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    WITH neg AS (
                        SELECT LOWER(COALESCE(social_meta->>'author','')) AS author,
                               publication_date, {_ENGAGEMENT_SQL} AS eng
                        FROM articles
                        WHERE topic = :t AND {_SOCIAL_SRC_SQL}
                          AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
                          AND COALESCE(social_meta->>'author','') <> ''
                          AND publication_date >= to_char(now() - (:lb || ' days')::interval,'YYYY-MM-DD')
                          AND {_not_fp_sql()}
                    )
                    SELECT author,
                           COUNT(*) FILTER (WHERE publication_date >= to_char(now() - (:rh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')) AS recent,
                           COUNT(*) FILTER (WHERE publication_date <  to_char(now() - (:rh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')) AS prior,
                           MAX(eng) FILTER (WHERE publication_date >= to_char(now() - (:rh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')) AS max_eng
                    FROM neg GROUP BY author
                    HAVING COUNT(*) FILTER (WHERE publication_date <  to_char(now() - (:rh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')) = 0
                """), {"t": topic, "lb": str(rc["lookback_days"]), "rh": str(rc["recent_hours"])}).fetchall()
                for author, recent, prior, max_eng in rows:
                    if _is_own_handle(author) or ':' in author:
                        continue
                    high_reach = (max_eng or 0) >= rc["min_engagement_single"]
                    # Keyed per author, no time bucket: an account is a "new
                    # critic" once — after that it's a known critic.
                    if ((recent or 0) >= rc["min_recent_neg"] or high_reach) \
                            and not _dedup_exists(conn, f"new_critic|{bid}|{author}"):
                        posts = fetch_negative_social_posts(
                            conn, topic, int(rc["recent_hours"]), author=author)
                        if _insert_alert_event(conn, bid, "new_critic",
                                "high" if high_reach else "medium",
                                f"{bname}: new critic @{author} ({recent} negative post{'s' if recent != 1 else ''})",
                                _social_body(
                                    f"@{author} posted {recent} negative post{'s' if recent != 1 else ''} about {bname} "
                                    f"in the last {rc['recent_hours']}h with no prior negative history in {rc['lookback_days']} days"
                                    + (f" (max engagement {int(max_eng)})." if max_eng else "."),
                                    bname, posts),
                                {"author": author, "recent": recent, "max_engagement": max_eng,
                                 "posts": _posts_payload(posts)},
                                f"new_critic|{bid}|{author}"):
                            created += 1

            # 8) Coordinated negativity: the same (normalized) negative message posted
            #    by several distinct accounts — copypasta/brigading, not organic backlash.
            rc = rule("coordinated_negative")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    SELECT LEFT(regexp_replace(lower(COALESCE(NULLIF(summary,''), title, '')),
                                '(https?://\\S+)|[^a-z0-9 ]', '', 'g'), 120) AS sig,
                           COUNT(DISTINCT social_meta->>'author') AS authors,
                           COUNT(*) AS n, MAX(title) AS sample
                    FROM articles
                    WHERE topic = :t AND {_SOCIAL_SRC_SQL}
                      AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
                      AND COALESCE(social_meta->>'author','') <> ''
                      AND publication_date >= to_char(now() - (:wh || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')
                      AND {_not_fp_sql()}
                    GROUP BY 1
                    HAVING LENGTH(LEFT(regexp_replace(lower(COALESCE(NULLIF(summary,''), title, '')),
                                '(https?://\\S+)|[^a-z0-9 ]', '', 'g'), 120)) > 30
                       AND COUNT(DISTINCT social_meta->>'author') >= :ma
                """), {"t": topic, "wh": str(rc["window_hours"]), "ma": rc["min_authors"]}).fetchall()
                for sig, authors, n, sample in rows:
                    if _insert_alert_event(conn, bid, "coordinated_negative", "high",
                            f"{bname}: possible coordinated negative campaign ({authors} accounts, same message)",
                            f"{n} negative posts from {authors} distinct accounts repeat the same message "
                            f"in the last {rc['window_hours']}h — copypasta pattern, not organic backlash. "
                            f"Sample: \"{(sample or '')[:120]}\"",
                            {"authors": authors, "posts": n, "signature": sig[:80]},
                            f"coordinated_negative|{bid}|{sig[:60]}"):
                        created += 1

            # 9) Glassdoor deterioration: latest snapshot vs the oldest within the
            # lookback window. Employer ratings move slowly — a 0.2 drop or a
            # 10-point outlook slide inside ~a month is a real signal.
            rc = rule("glassdoor_deterioration")
            if rc.get("enabled"):
                snaps = conn.execute(_text("""
                    (SELECT snapshot_date, data FROM bw_glassdoor_snapshots
                     WHERE brand_id = :b
                       AND snapshot_date >= CURRENT_DATE - (:lb || ' days')::interval
                     ORDER BY snapshot_date ASC LIMIT 1)
                    UNION ALL
                    (SELECT snapshot_date, data FROM bw_glassdoor_snapshots
                     WHERE brand_id = :b ORDER BY snapshot_date DESC LIMIT 1)
                """), {"b": bid, "lb": str(rc["lookback_days"])}).fetchall()
                if len(snaps) == 2 and snaps[0][0] != snaps[1][0]:
                    (d_old, old_data), (d_new, new_data) = snaps
                    if (d_new - d_old).days >= rc.get("min_span_days", 7):
                        o = old_data if isinstance(old_data, dict) else _json.loads(old_data or "{}")
                        n2 = new_data if isinstance(new_data, dict) else _json.loads(new_data or "{}")
                        drops = []
                        try:
                            r_old, r_new = o.get("rating"), n2.get("rating")
                            if r_old is not None and r_new is not None and (r_old - r_new) >= rc["rating_drop"]:
                                drops.append(f"overall rating {r_old} → {r_new}")
                            ol_old, ol_new = o.get("business_outlook_rating"), n2.get("business_outlook_rating")
                            if ol_old is not None and ol_new is not None and (ol_old - ol_new) >= rc["outlook_drop"]:
                                drops.append(f"business outlook {round(ol_old*100)}% → {round(ol_new*100)}%")
                        except TypeError:
                            drops = []
                        if drops:
                            if _insert_alert_event(conn, bid, "glassdoor_deterioration", "medium",
                                    f"{bname}: Glassdoor employer ratings deteriorating",
                                    f"Since {d_old}: " + "; ".join(drops)
                                    + ". Employer ratings move slowly — a slide this size in "
                                    f"{(d_new - d_old).days} days usually reflects a real internal shift.",
                                    {"from": str(d_old), "to": str(d_new),
                                     "rating_old": o.get("rating"), "rating_new": n2.get("rating"),
                                     "outlook_old": o.get("business_outlook_rating"),
                                     "outlook_new": n2.get("business_outlook_rating")},
                                    f"glassdoor_deterioration|{bid}|{d_old}|{d_new}"):
                                created += 1

            # 10) Five Signals screen failure: a screened article whose claim
            #     validation came back contested/non-independent, or whose social
            #     pickup shows coordinated amplification. Fires once per article
            #     (dedup has no time bucket) — the verdict on an article is final.
            rc = rule("signals_flag")
            if rc.get("enabled"):
                rows = conn.execute(_text(f"""
                    SELECT s.article_uri, s.verdict, s.composite_score, s.signals, a.title
                    FROM bw_article_signals s JOIN articles a ON a.uri = s.article_uri
                    WHERE s.brand_id = :b AND s.status = 'completed'
                      AND s.updated_at >= now() - (:rd || ' days')::interval
                      AND {_not_fp_sql('a')}
                """), {"b": bid, "rd": str(rc.get("recent_days", 7))}).fetchall()
                for s_uri, s_verdict, s_comp, s_sigs, s_title in rows:
                    sp = s_sigs if isinstance(s_sigs, dict) else _json.loads(s_sigs or "{}")
                    amp = sp.get("amplification_integrity") or {}
                    bad_verdict = s_verdict in ("contested", "non_independent")
                    bad_amp = amp.get("band") == "bad"
                    if not (bad_verdict or bad_amp):
                        continue
                    reasons = []
                    if bad_verdict:
                        reasons.append(f"claim validation verdict '{s_verdict}'")
                    if bad_amp and amp.get("summary"):
                        reasons.append(amp["summary"].rstrip("."))
                    if _insert_alert_event(conn, bid, "signals_flag", "high",
                            f"{bname}: article fails Five Signals screen",
                            f"\"{(s_title or '')[:120]}\" — " + "; ".join(reasons)
                            + f". Composite screen score {s_comp}.",
                            {"article_uri": s_uri, "verdict": s_verdict,
                             "composite_score": s_comp,
                             "amplification_band": amp.get("band")},
                            f"signals_flag|{bid}|{s_uri}"):
                        created += 1

        conn.commit()
        # Push whatever is new through the configured channels.
        try:
            deliver_pending_events(db, conn)
        except Exception as de:
            logger.error(f"Adverse alert delivery failed: {de}")
        if created:
            logger.info(f"Adverse alert evaluation created {created} new event(s)")
        return created
    except Exception as e:
        logger.error(f"Adverse alert evaluation failed: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


AUTO_SIGNALS_DAILY_CAP = 10   # fresh saas screens cost LLM + web-search calls
AUTO_SIGNALS_PER_CYCLE = 2    # each run is 2-4 min; keep the loop responsive


async def _auto_screen_high_risk(db) -> None:
    """Run Five Signals on articles that just picked up a high-severity finding.

    Analysts scrutinize these anyway — pre-running the screen means the verdict
    is waiting when they open the article. Bounded two ways: per cycle (the
    runs are awaited inline) and per day across all brands.
    """
    from app.services.bw_signals_service import signals_available, run_five_signals
    if not signals_available():
        return
    conn = db._temp_get_connection()
    try:
        today_auto = conn.execute(text("""
            SELECT COUNT(*) FROM bw_article_signals
            WHERE requested_by = 'auto' AND created_at >= CURRENT_DATE
        """)).fetchone()[0]
        budget = min(AUTO_SIGNALS_PER_CYCLE, AUTO_SIGNALS_DAILY_CAP - today_auto)
        if budget <= 0:
            return
        candidates = conn.execute(text("""
            SELECT DISTINCT r.article_uri, r.brand_id
            FROM bw_article_risks r
            JOIN bw_brands b ON b.id = r.brand_id AND b.enabled = true
            JOIN articles a ON a.uri = r.article_uri
            LEFT JOIN bw_article_signals s
              ON s.article_uri = r.article_uri AND s.brand_id = r.brand_id
            WHERE r.severity = 'high'
              AND r.detected_at >= now() - interval '48 hours'
              AND s.id IS NULL
              AND (a.uri ILIKE 'http://%' OR a.uri ILIKE 'https://%')
            ORDER BY r.article_uri
            LIMIT :lim
        """), {"lim": budget}).fetchall()
    finally:
        conn.close()
    for uri, brand_id in candidates:
        logger.info(f"Five Signals auto-screen: {uri} (brand {brand_id})")
        await run_five_signals(uri, brand_id, uri, requested_by="auto")


async def run_brand_watcher_monitor():
    """Background task to periodically check and run scheduled brand watcher classification."""
    global _background_task_status

    db = Database()
    monitor = BrandWatcherMonitor(db)

    logger.info("Brand watcher monitor background task started")
    _background_task_status["running"] = True

    check_interval = 60
    retrain_check_counter = 0
    adverse_counter = 13  # first adverse evaluation ~2 min after startup
    official_counter = 2  # first official-sources check ~3 min after startup
    social_sweep_counter = 3  # hourly: retry social posts whose eval failed

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            # Get schedules that are due to run
            due_schedules = monitor.get_due_schedules()
            _background_task_status["schedules_checked"] = len(due_schedules)

            if due_schedules:
                logger.info(f"Found {len(due_schedules)} brand watcher schedules due to run")

                for schedule in due_schedules:
                    try:
                        result = await monitor.run_schedule(schedule)
                        if result["success"]:
                            _background_task_status["schedules_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running brand watcher schedule {schedule.get('name')}: {e}")

            # Adverse-media alert rules every ~15 cycles (~15 min)
            adverse_counter += 1
            if adverse_counter >= 15:
                adverse_counter = 0
                try:
                    # Off-loop: rule evaluation now narrates the posts behind
                    # social alerts (blocking LLM call) before persisting them.
                    await asyncio.to_thread(evaluate_adverse_alerts, db)
                except Exception as e:
                    logger.error(f"Adverse alert evaluation error: {e}")
                # Digest is hour-gated + period-deduped internally — cheap to check here.
                # Off-loop: the digest composes an LLM prose lead + sends SMTP,
                # both blocking calls that must not run on the event loop.
                try:
                    from app.services.bw_digest_service import maybe_send_digest
                    await asyncio.to_thread(maybe_send_digest, db)
                except Exception as e:
                    logger.error(f"Digest check error: {e}")
                # Auto Five Signals screening of fresh high-severity findings
                # (daily-capped; no-op when the saas key is absent).
                try:
                    await _auto_screen_high_risk(db)
                except Exception as e:
                    logger.error(f"Five Signals auto-screen error: {e}")
                # Re-poll engagement for on-brand social posts 6h-7d old (collection
                # snapshots metrics at age ~0, so reach reads 0 forever otherwise).
                # Per-post ~12h budget inside; sync SDK + HTTP, so off-loop.
                try:
                    from app.services.social_engagement_refresh import refresh_social_engagement
                    await asyncio.to_thread(refresh_social_engagement, db, 300)
                except Exception as e:
                    logger.error(f"Engagement refresh error: {e}")
                # Hourly (every 4th adverse cycle): retry social posts whose
                # relevance/sentiment eval failed (model timeouts/outages leave
                # them unscored and invisible to the relevance-filtered views;
                # the per-group collection cycle was previously the only retry).
                social_sweep_counter += 1
                if social_sweep_counter >= 4:
                    social_sweep_counter = 0
                    try:
                        from app.services.social_eval_service import sweep_unevaluated_social
                        await sweep_unevaluated_social(db)
                    except Exception as e:
                        logger.error(f"Social eval sweep error: {e}")

            # Official/scholarly sources every ~5 cycles; the per-(brand, source)
            # 24h cursor inside makes a no-op cycle one SELECT.
            official_counter += 1
            if official_counter >= 5:
                official_counter = 0
                try:
                    from app.services.bw_official_sources import poll_official_sources
                    await poll_official_sources(db)
                except Exception as e:
                    logger.error(f"Official sources poll error: {e}")

            # Check auto-retrain every ~60 monitor cycles (~1 hour)
            retrain_check_counter += 1
            if retrain_check_counter >= 60:
                retrain_check_counter = 0
                try:
                    _check_auto_retrain(db)
                except Exception as e:
                    logger.error(f"Auto-retrain check failed: {e}")
                # Foreign-language relevance recovery (bounded LLM budget per run;
                # attempted articles are stamped, so this converges).
                try:
                    from app.services.bw_language_recovery import recover_foreign_articles
                    await recover_foreign_articles(db, limit=20)
                except Exception as e:
                    logger.error(f"Language recovery error: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Brand watcher monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        await asyncio.sleep(check_interval)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    """Run a specific schedule immediately (for manual triggering)."""
    monitor = BrandWatcherMonitor(db)

    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, brand_id, run_type, days_back, topics,
                   schedule_type, schedule_interval, schedule_unit, schedule_time,
                   last_run_at, next_run_at, run_count,
                   notify_on_complete, notify_threshold
            FROM bw_tracker_schedules
            WHERE id = :id
        """), {"id": schedule_id})
        row = result.mappings().first()
        conn.close()

        if not row:
            return {"success": False, "error": "Schedule not found"}

        schedule = dict(row)
        return await monitor.run_schedule(schedule)

    except Exception as e:
        return {"success": False, "error": str(e)}
