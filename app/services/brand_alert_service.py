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

# Mirrors the evaluator's sentiment/engagement SQL (app/tasks/brand_watcher_monitor.py) —
# kept here so both the evaluator and the digest can pull the posts behind an alert
# without a services -> tasks import.
_NEG_SENT_SQL = ("(sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR sentiment ILIKE '%pessimis%'"
                 " OR sentiment ILIKE '%critical%' OR sentiment ILIKE '%alarm%')")
_ENGAGEMENT_SQL = ("(COALESCE((social_meta->>'likes')::float,0) + 2*COALESCE((social_meta->>'reposts')::float,0)"
                   " + COALESCE((social_meta->>'comments')::float,0) + COALESCE((social_meta->>'plays')::float,0)/100)")


def fetch_negative_social_posts(conn, topic: str, hours: int, author: Optional[str] = None,
                                min_engagement: Optional[float] = None, limit: int = 6) -> List[Dict[str, Any]]:
    """The negative on-brand social posts behind a social alert, most-engaged first.

    Same predicates as the alert rules themselves (topic lane, alignment >= 0.4,
    negative sentiment, false-positive exclusion), so the posts shown are exactly
    the ones that were counted.
    """
    from app.services.social_sources import social_src_sql
    params: Dict[str, Any] = {"t": topic, "h": str(hours), "lim": limit}
    extra = ""
    if author:
        extra += " AND LOWER(COALESCE(social_meta->>'author','')) = :author"
        params["author"] = author.lower()
    if min_engagement is not None:
        extra += f" AND {_ENGAGEMENT_SQL} >= :min_eng"
        params["min_eng"] = min_engagement
    rows = conn.execute(text(f"""
        SELECT title, uri, news_source, LEFT(COALESCE(NULLIF(summary,''), title, ''), 400),
               COALESCE(social_meta->>'author',''), {_ENGAGEMENT_SQL} AS eng
        FROM articles
        WHERE topic = :t AND {social_src_sql('news_source')}
          AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
          AND publication_date >= to_char(now() - (:h || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')
          AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews _fpr
                          WHERE _fpr.article_uri = articles.uri AND _fpr.status = 'false_positive')
          {extra}
        ORDER BY eng DESC NULLS LAST, publication_date DESC
        LIMIT :lim
    """), params).fetchall()
    return [{"title": r[0] or "", "url": r[1], "source": r[2] or "", "text": r[3] or "",
             "author": r[4] or "", "engagement": round(float(r[5] or 0))} for r in rows]


def _platform_label(source: str) -> str:
    """Reader-facing platform name from the internal news_source ('xpoz:twitter' → 'X/Twitter')."""
    s = (source or "").lower().split(":")[-1]
    return {"twitter": "X/Twitter", "reddit": "Reddit", "instagram": "Instagram",
            "tiktok": "TikTok", "bluesky": "Bluesky", "bsky": "Bluesky",
            "youtube": "YouTube", "reddit.com": "Reddit"}.get(s, source or "")


def narrate_social_posts(brand: str, posts: List[Dict[str, Any]]) -> Optional[str]:
    """2-3 plain sentences on what the posts actually say. Best-effort: None on failure,
    and the alert ships with the linked post list only."""
    if not posts:
        return None
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        block = "\n".join(
            f"- {_platform_label(p['source'])} · @{p['author'] or 'unknown'}: {(p['text'] or p['title'])[:350]}"
            for p in posts[:8]
        )
        prompt = (
            f"Negative social posts about the brand \"{brand}\" (platform · author: post):\n"
            + block[:3500]
            + "\n\nIn 2-3 plain sentences, say what these posts are actually saying — the "
            "concrete complaints, claims or stories, named specifically, and who is saying "
            "them when it matters (one loud account, a single community, many unrelated "
            "users). Observations only, nothing not present in the posts. No preamble, "
            "no bullets — just the sentence(s)."
        )
        out = (model.generate_response(
            [{"role": "user", "content": prompt}], temperature=0.2) or "").strip()
        if not out or out.startswith(("-", "*", "#")):
            return None
        return out[:700]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"bw social-post narration failed for {brand}: {e}")
        return None


def social_posts_md(posts: List[Dict[str, Any]], limit: int = 5, indent: str = "") -> List[str]:
    """Markdown bullets for the posts behind an alert: linked text — @author · platform · engagement."""
    lines = []
    for p in posts[:limit]:
        t = (p.get("title") or p.get("text") or "").replace("\\n", " ").replace("\\t", " ")
        t = " ".join(t.split())[:110].replace("[", "(").replace("]", ")")
        link = f"[{t}]({p['url']})" if str(p.get("url") or "").startswith("http") else t
        bits = [b for b in (f"@{p['author']}" if p.get("author") else "",
                            _platform_label(p.get("source") or ""),
                            f"engagement {p['engagement']}" if p.get("engagement") else "") if b]
        lines.append(f"{indent}- {link}" + (" — " + " · ".join(bits) if bits else ""))
    return lines


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
        # Release gate (advisory) — logs internal-name leaks and similar
        # defects before the alert reaches a customer inbox.
        try:
            from app.services.report_lint import lint_outbound
            lint_outbound(body_md, kind="html", context="bw_alert_email")
        except Exception:
            pass
        ok = svc.send_email(
            to_addresses=recipients,
            subject=f"[AuNoo AI] Brand alert: {event['title'][:120]}",
            body_html=markdown_to_html(body_md),
            body_text=f"{event['title']}\n\n{event.get('body') or ''}\n{link}",
            ai_generated=True,
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
        FROM bw_alert_events WHERE delivered IS NULL AND rule <> 'digest'
        ORDER BY id LIMIT 50
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
