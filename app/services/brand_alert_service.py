"""Brand Watcher adverse-media alert delivery.

Takes persisted bw_alert_events rows that have not been delivered yet and pushes
them through the configured channels:
  - in_app   -> notifications table (NotificationBell UI picks it up)
  - email    -> EmailService (Resend/SMTP), template modelled on send_signal_alert_email
  - webhook  -> JSON POST (Slack-incoming-webhook compatible: includes "text")

Config lives in bw_alert_config (rules/thresholds are consumed by the evaluator in
app/tasks/brand_watcher_monitor.py; this module only handles delivery).
"""
import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def get_alert_config(conn) -> Optional[Dict[str, Any]]:
    """Load the tenant-wide alert config row (brand_id NULL). Returns None if absent."""
    row = conn.execute(text("""
        SELECT id, enabled, rules, channels, email_recipients, webhook_url, cooldown_hours
        FROM bw_alert_config WHERE brand_id IS NULL ORDER BY id LIMIT 1
    """)).fetchone()
    if not row:
        return None
    def _j(v, default):
        if v is None:
            return default
        return v if isinstance(v, (dict, list)) else json.loads(v)
    return {
        "id": row[0], "enabled": row[1],
        "rules": _j(row[2], {}), "channels": _j(row[3], {}),
        "email_recipients": _j(row[4], []), "webhook_url": row[5],
        "cooldown_hours": row[6] or 24,
    }


def _deliver_in_app(db, event: Dict[str, Any]) -> bool:
    try:
        db.facade.create_notification(
            username=None,  # system-wide
            type="brand_watcher_adverse",
            title=event["title"],
            message=(event.get("body") or "")[:500],
            link="/explore",
        )
        return True
    except Exception as e:
        logger.warning(f"bw alert in_app delivery failed: {e}")
        return False


def _deliver_email(event: Dict[str, Any], recipients: List[str]) -> bool:
    if not recipients:
        return False
    try:
        from app.services.email_service import get_email_service, markdown_to_html
        svc = get_email_service()
        if not svc.is_available():
            logger.warning("bw alert email skipped: email service not configured")
            return False
        sev = event.get("severity", "medium")
        domain = os.getenv("DOMAIN", "")
        link = f"https://{domain}/explore" if domain else ""
        body_md = (
            f"**{SEVERITY_EMOJI.get(sev, '')} {event['title']}**\n\n"
            f"{event.get('body') or ''}\n\n"
            + (f"[Open Brand Watcher]({link})\n" if link else "")
        )
        ok = svc.send_email(
            to_addresses=recipients,
            subject=f"[AuNoo AI] Brand alert: {event['title'][:120]}",
            body_html=markdown_to_html(body_md),
            body_text=f"{event['title']}\n\n{event.get('body') or ''}\n{link}",
        )
        return bool(ok)
    except Exception as e:
        logger.warning(f"bw alert email delivery failed: {e}")
        return False


def _deliver_webhook(event: Dict[str, Any], url: str) -> bool:
    if not url:
        return False
    try:
        sev = event.get("severity", "medium")
        payload = {
            # "text" makes this drop-in compatible with Slack incoming webhooks.
            "text": f"{SEVERITY_EMOJI.get(sev, '')} Brand alert ({sev}): {event['title']}\n{event.get('body') or ''}",
            "rule": event.get("rule"),
            "severity": sev,
            "brand_id": event.get("brand_id"),
            "payload": event.get("payload"),
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        logger.warning(f"bw alert webhook delivery failed: {e}")
        return False


def deliver_pending_events(db, conn) -> int:
    """Deliver all bw_alert_events rows with delivered IS NULL. Returns count delivered."""
    cfg = get_alert_config(conn)
    if not cfg or not cfg["enabled"]:
        return 0
    channels = cfg["channels"] or {}
    rows = conn.execute(text("""
        SELECT id, brand_id, rule, severity, title, body, payload
        FROM bw_alert_events WHERE delivered IS NULL ORDER BY id LIMIT 50
    """)).fetchall()
    done = 0
    for rid, brand_id, rule, severity, title, body, payload in rows:
        event = {"id": rid, "brand_id": brand_id, "rule": rule, "severity": severity,
                 "title": title, "body": body, "payload": payload}
        delivered: Dict[str, bool] = {}
        if channels.get("in_app", True):
            delivered["in_app"] = _deliver_in_app(db, event)
        if channels.get("email"):
            delivered["email"] = _deliver_email(event, cfg["email_recipients"])
        if channels.get("webhook"):
            delivered["webhook"] = _deliver_webhook(event, cfg["webhook_url"])
        conn.execute(text("UPDATE bw_alert_events SET delivered = :d WHERE id = :i"),
                     {"d": json.dumps(delivered), "i": rid})
        done += 1
        logger.info(f"bw alert delivered #{rid} [{rule}/{severity}] via {[k for k, v in delivered.items() if v]}")
    if done:
        conn.commit()
    return done
