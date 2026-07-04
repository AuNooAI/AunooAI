"""Brand Watcher adverse-media digest email (daily/weekly).

Composes a compact cross-brand digest — new alert events, risk findings, case
actions, sentiment nets — and emails it to the alert recipients. Settings live
in ``bw_alert_config.channels['digest']``: {enabled, frequency: daily|weekly,
hour_utc}. Idempotence rides the bw_alert_events dedup_key (rule='digest',
one key per calendar period), so restarts and multi-cycle checks can't double-send.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_NEG = ("sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR sentiment ILIKE '%pessimis%'"
        " OR sentiment ILIKE '%critical%' OR sentiment ILIKE '%alarm%'")
_POS = "(sentiment ILIKE '%positiv%' OR sentiment ILIKE '%optimis%')"


def _compose_digest(conn, period_days: int) -> Optional[str]:
    """Markdown digest body across enabled brands; None when there is nothing to say."""
    brands = conn.execute(text(
        "SELECT id, display_name FROM bw_brands WHERE enabled = true ORDER BY is_primary DESC, display_name"
    )).fetchall()
    # First pass: per-brand news nets, so each section can benchmark against the
    # average of the OTHER brands ("are we worse, or is the whole sector down?").
    nets: dict = {}
    stats: dict = {}
    for bid, bname in brands:
        row = conn.execute(text(f"""
            SELECT COUNT(*) FILTER (WHERE {_POS}) AS pos,
                   COUNT(*) FILTER (WHERE {_NEG}) AS neg,
                   COUNT(*) FILTER (WHERE COALESCE(sentiment,'') <> '') AS scored
            FROM articles a
            JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
            WHERE a.publication_date >= to_char(now() - (:d || ' days')::interval,'YYYY-MM-DD')
              AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
        """), {"b": bid, "d": str(period_days)}).fetchone()
        pos, neg, scored = row[0] or 0, row[1] or 0, row[2] or 0
        stats[bid] = (pos, neg, scored)
        nets[bid] = round(((pos - neg) / scored) * 100) if scored >= 3 else None
    lines = []
    had_content = False
    for bid, bname in brands:
        section = []
        pos, neg, scored = stats[bid]
        net = round(((pos - neg) / scored) * 100) if scored else None
        if scored:
            comp = [v for k, v in nets.items() if k != bid and v is not None]
            comp_avg = round(sum(comp) / len(comp)) if comp else None
            bench = ""
            if net is not None and comp_avg is not None:
                d = net - comp_avg
                bench = f" — competitor avg {'+' if comp_avg > 0 else ''}{comp_avg} ({'+' if d > 0 else ''}{d})"
            section.append(f"- News sentiment: **{'+' if net and net > 0 else ''}{net}** "
                           f"({pos}+ / {neg}− of {scored} scored){bench}")
        # New risk findings.
        risks = conn.execute(text("""
            SELECT r.risk_type, r.severity, LEFT(a.title, 90)
            FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
            WHERE r.brand_id = :b AND r.detected_at >= now() - (:d || ' days')::interval
            ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT 5
        """), {"b": bid, "d": str(period_days)}).fetchall()
        for rt, sev, title in risks:
            section.append(f"- ⚠ **{rt.replace('_', '/')}** ({sev}): {title}")
        # Alert events fired.
        events = conn.execute(text("""
            SELECT title FROM bw_alert_events
            WHERE brand_id = :b AND rule <> 'digest'
              AND created_at >= now() - (:d || ' days')::interval
            ORDER BY created_at DESC LIMIT 5
        """), {"b": bid, "d": str(period_days)}).fetchall()
        for (title,) in events:
            section.append(f"- 🔔 {title}")
        # Case actions taken.
        row = conn.execute(text("""
            SELECT COUNT(*) FILTER (WHERE new_status = 'escalated') AS esc,
                   COUNT(*) FILTER (WHERE new_status = 'reviewed') AS rev,
                   COUNT(*) FILTER (WHERE new_status = 'dismissed') AS dis
            FROM bw_finding_review_log
            WHERE brand_id = :b AND at >= now() - (:d || ' days')::interval
        """), {"b": bid, "d": str(period_days)}).fetchone()
        esc, rev, dis = row[0] or 0, row[1] or 0, row[2] or 0
        if esc + rev + dis:
            section.append(f"- Case actions: {esc} escalated · {rev} reviewed · {dis} dismissed")
        if section:
            had_content = True
            lines.append(f"### {bname}")
            lines.extend(section)
            lines.append("")
    if not had_content:
        return None
    return "\n".join(lines)


def maybe_send_digest(db) -> bool:
    """Send the digest if one is due for the current period. Returns True when sent."""
    from app.services.brand_alert_service import get_alert_config
    conn = db._temp_get_connection()
    try:
        cfg = get_alert_config(conn)
        if not cfg or not cfg.get("enabled"):
            return False
        dg = (cfg.get("channels") or {}).get("digest") or {}
        if not dg.get("enabled"):
            return False
        recipients = cfg.get("email_recipients") or []
        if not recipients:
            return False
        freq = dg.get("frequency", "daily")
        hour = int(dg.get("hour_utc", 6))
        now = datetime.now(timezone.utc)
        if now.hour != hour:
            return False
        if freq == "weekly" and now.weekday() != 0:  # Mondays
            return False
        period_days = 7 if freq == "weekly" else 1
        marker = now.strftime("%Y-W%W") if freq == "weekly" else now.strftime("%Y-%m-%d")
        # Claim the period atomically — a second cycle in the same hour inserts nothing.
        claimed = conn.execute(text("""
            INSERT INTO bw_alert_events (brand_id, rule, severity, title, body, payload, dedup_key)
            VALUES (NULL, 'digest', 'low', :t, '', '{}', :k)
            ON CONFLICT (dedup_key) DO NOTHING RETURNING id
        """), {"t": f"Adverse-media digest ({freq})", "k": f"digest|{marker}"}).fetchone()
        conn.commit()
        if not claimed:
            return False
        body_md = _compose_digest(conn, period_days)
        if body_md is None:
            body_md = "_Quiet period — no new findings, alerts, or case actions._"
        title = f"Adverse-media digest — {'last 7 days' if freq == 'weekly' else 'last 24 hours'}"
        try:
            from app.services.email_service import get_email_service, markdown_to_html
            svc = get_email_service()
            if not svc.is_available():
                logger.warning("bw digest skipped: email service not configured")
                return False
            # The text/plain alternative must NOT carry markdown syntax — clients
            # that prefer (or preview) the text part would show it literally.
            text_body = re.sub(r"^### (.+)$", r"\1", body_md, flags=re.MULTILINE)
            text_body = text_body.replace("**", "").replace("_Quiet period", "Quiet period").rstrip("_")
            ok = svc.send_email(
                to_addresses=recipients,
                subject=f"[AuNoo AI] {title}",
                body_html=markdown_to_html(f"## {title}\n\n{body_md}"),
                body_text=f"{title}\n\n{text_body}",
            )
            conn.execute(text("UPDATE bw_alert_events SET delivered = :d, body = :b WHERE id = :i"),
                         {"d": json.dumps({"email": bool(ok)}), "b": text_body[:5000], "i": claimed[0]})
            conn.commit()
            logger.info(f"bw digest sent to {len(recipients)} recipient(s): {bool(ok)}")
            return bool(ok)
        except Exception as e:
            logger.error(f"bw digest send failed: {e}")
            return False
    finally:
        conn.close()
