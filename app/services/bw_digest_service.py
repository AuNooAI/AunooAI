"""Brand Watcher adverse-media digest email (daily/weekly).

Composes a compact cross-brand digest — new alert events, risk findings, case
actions, sentiment nets — and emails it to the alert recipients. Settings live
in ``bw_alert_config.channels['digest']``: {enabled, frequency: daily|weekly,
hour_utc}. Idempotence rides the bw_alert_events dedup_key (rule='digest',
one key per calendar period), so restarts and multi-cycle checks can't double-send.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_NEG = ("sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR sentiment ILIKE '%pessimis%'"
        " OR sentiment ILIKE '%critical%' OR sentiment ILIKE '%alarm%'")
_POS = "(sentiment ILIKE '%positiv%' OR sentiment ILIKE '%optimis%')"

_BASE_URL = os.getenv("APP_PUBLIC_URL", "https://wbm.aunoo.ai").rstrip("/")
_DASHBOARD_URL = f"{_BASE_URL}/newsfeed?tab=brand-watcher"


def _md_link(title: str, url: Optional[str]) -> str:
    """Markdown link with bracket-safe title; falls back to plain text."""
    t = (title or "").replace("[", "(").replace("]", ")")
    if not url or not str(url).startswith("http"):
        return t
    return f"[{t}]({url})"


def _brand_narration(brand: str, alert_titles: list, articles: list) -> Optional[str]:
    """1-2 sentence narration of what is behind a brand's alerts.

    Grounded in the driver articles' titles + summaries only. Best-effort:
    returns None on failure and the digest ships with bare headline links.
    """
    if not articles:
        return None
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        art_block = "\n".join(
            f"- {t}: {sm}" if sm else f"- {t}" for t, sm in articles[:6]
        )
        prompt = (
            f"Alerts fired for the brand \"{brand}\":\n"
            + "\n".join(f"- {t}" for t in alert_titles[:5])
            + "\n\nThe articles behind them (title: summary):\n" + art_block[:3500]
            + "\n\nIn 1-2 plain sentences, say what this coverage is actually "
            "about — the concrete stories/themes, named specifically. "
            "Observations only, no advice, nothing not present in the "
            "articles. No preamble, no bullets — just the sentence(s)."
        )
        out = (model.generate_response(
            [{"role": "user", "content": prompt}], temperature=0.2) or "").strip()
        if not out or out.startswith(("-", "*", "#")):
            return None
        return out[:600]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"bw digest narration failed for {brand} ({e})")
        return None


def _prose_summary(facts: str, period_label: str) -> Optional[str]:
    """2-4 sentence editorial lead over the deterministic digest facts.

    Grounded strictly in the composed bullet facts (no raw-article access,
    so it cannot introduce out-of-period claims). Best-effort: any failure
    returns None and the digest ships without a lead. Runs on the mini
    (Haiku) route — the caller already runs off the event loop.
    """
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance("gpt-5.4-mini")
        prompt = (
            "You are writing the one-paragraph lead for an adverse-media digest "
            f"email covering the {period_label}. Below are ALL the facts, as "
            "bullet points per brand. Write 2-4 plain sentences a comms analyst "
            "would skim: name the brands that need attention first, say what "
            "changed and how bad it is relative to peers, and note anything "
            "quiet/stable in half a sentence. Observations only — no advice, no "
            "recommendations. Never state a number or fact that is not in the "
            "bullets. Net-sentiment numbers: MORE NEGATIVE = WORSE (-38 is "
            "worse than -26) — do not compare them the wrong way round. No "
            "greeting, no markdown, no bullet points — just the "
            "paragraph.\n\nFACTS:\n" + facts[:6000]
        )
        out = model.generate_response(
            [{"role": "user", "content": prompt}], temperature=0.2)
        out = (out or "").strip()
        # Guard against a model returning markdown/bullets anyway.
        if not out or out.startswith(("-", "*", "#")):
            return None
        return out[:1200]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"bw digest prose lead failed ({e}) — sending without it")
        return None


def _compose_digest(conn, period_days: int) -> Optional[str]:
    """Markdown digest body across enabled brands; None when there is nothing to say."""
    brands = conn.execute(text(
        "SELECT id, display_name, COALESCE(config, '{}') FROM bw_brands "
        "WHERE enabled = true ORDER BY is_primary DESC, display_name"
    )).fetchall()
    # First pass: per-brand news nets, so each section can benchmark against the
    # average of the OTHER brands ("are we worse, or is the whole sector down?").
    nets: dict = {}
    stats: dict = {}
    for bid, bname, _bcfg in brands:
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
    for bid, bname, bcfg in brands:
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
        # Employee signal (cached Glassdoor aggregates + reviews landed this period).
        _cfg = bcfg if isinstance(bcfg, dict) else json.loads(bcfg or "{}")
        _gd = ((_cfg.get("glassdoor_overview") or {}).get("data")) or None
        if _gd and _gd.get("rating") is not None:
            _gr = conn.execute(text(f"""
                SELECT COUNT(*) FILTER (WHERE {_POS}) AS pos,
                       COUNT(*) FILTER (WHERE {_NEG}) AS neg
                FROM articles a
                JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
                WHERE a.news_source = 'Glassdoor'
                  AND a.publication_date >= to_char(now() - (:d || ' days')::interval,'YYYY-MM-DD')
            """), {"b": bid, "d": str(period_days)}).fetchone()
            _outlook = _gd.get("business_outlook_rating")
            _bits = [f"{_gd['rating']}★ Glassdoor"]
            if _outlook is not None:
                _bits.append(f"outlook {round(_outlook * 100)}%")
            if (_gr[0] or 0) + (_gr[1] or 0):
                _bits.append(f"reviews this period {_gr[0] or 0}+ / {_gr[1] or 0}−")
            section.append("- Employee signal: " + " · ".join(_bits))
        # New risk findings — titles link to the underlying article (uri is
        # the article URL in this schema).
        risks = conn.execute(text("""
            SELECT r.risk_type, r.severity, LEFT(a.title, 90), a.uri
            FROM bw_article_risks r JOIN articles a ON a.uri = r.article_uri
            WHERE r.brand_id = :b AND r.detected_at >= now() - (:d || ' days')::interval
            ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT 5
        """), {"b": bid, "d": str(period_days)}).fetchall()
        for rt, sev, title, uri in risks:
            section.append(f"- ⚠ **{rt.replace('_', '/')}** ({sev}): {_md_link(title, uri)}")
        # Alert events fired. DISTINCT ON title: the same rule re-firing across
        # the period (e.g. daily-keyed sentiment alerts spanning two calendar
        # days) previously produced duplicate lines in the digest.
        events = conn.execute(text("""
            SELECT title, payload FROM (
                SELECT DISTINCT ON (title) title, payload, created_at FROM bw_alert_events
                WHERE brand_id = :b AND rule <> 'digest'
                  AND created_at >= now() - (:d || ' days')::interval
                ORDER BY title, created_at DESC
            ) t ORDER BY created_at DESC LIMIT 5
        """), {"b": bid, "d": str(period_days)}).fetchall()
        spike_cats: list = []
        has_neg_alert = False
        for title, payload in events:
            section.append(f"- 🔔 {title}")
            p = payload if isinstance(payload, dict) else json.loads(payload or "{}")
            if p.get("category"):
                spike_cats.append(p["category"])
            if "net-negative" in (title or ""):
                has_neg_alert = True

        # Driver articles behind the alerts — the digest should say WHAT the
        # coverage is, not just count it. Spike alerts measure a weekly
        # window, so their drivers are fetched over 7 days regardless of the
        # digest period; sentiment drivers stay within the digest period.
        drivers: list = []
        seen_uris: set = set()
        if spike_cats:
            cat_keys = {f"_c{i}": c for i, c in enumerate(spike_cats)}
            cat_in = ", ".join(f":{k}" for k in cat_keys)
            for t, u, s, sm in conn.execute(text(f"""
                SELECT a.title, a.uri, a.news_source, LEFT(COALESCE(a.summary,''), 300)
                FROM articles a
                JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
                WHERE bac.category IN ({cat_in})
                  AND a.publication_date >= to_char(now() - interval '7 days','YYYY-MM-DD')
                ORDER BY a.publication_date DESC LIMIT 4
            """), {"b": bid, **cat_keys}).fetchall():
                if u not in seen_uris:
                    seen_uris.add(u)
                    drivers.append((t, u, s, sm))
        if has_neg_alert or (neg or 0) >= 3:
            # Sentiment alerts aggregate over a wider window than a daily
            # digest period — fetch drivers over 7 days so the narration can
            # actually cover what the alert measured.
            for t, u, s, sm in conn.execute(text(f"""
                SELECT a.title, a.uri, a.news_source, LEFT(COALESCE(a.summary,''), 300)
                FROM articles a
                JOIN bw_article_categories bac ON bac.article_uri = a.uri AND bac.brand_id = :b
                WHERE ({_NEG})
                  AND a.publication_date >= to_char(now() - interval '7 days','YYYY-MM-DD')
                  AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                ORDER BY a.publication_date DESC LIMIT 4
            """), {"b": bid}).fetchall():
                if u not in seen_uris:
                    seen_uris.add(u)
                    drivers.append((t, u, s, sm))
        if drivers:
            narration = _brand_narration(
                bname,
                [t for t, _ in events],
                [(t, sm) for t, _, _, sm in drivers],
            )
            if narration:
                section.append(f"- What's driving it: {narration}")
            for t, u, s, _sm in drivers[:4]:
                src = f" — {s}" if s else ""
                section.append(f"    - {_md_link((t or '')[:90], u)}{src}")
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
        title = f"Adverse-media digest — {'last 7 days' if freq == 'weekly' else 'last 24 hours'}"
        if body_md is None:
            body_md = "_Quiet period — no new findings, alerts, or case actions._"
        else:
            period_label = "last 7 days" if freq == "weekly" else "last 24 hours"
            lead = _prose_summary(body_md, period_label)
            if lead:
                body_md = f"{lead}\n\n{body_md}"
        body_md += f"\n\n[Open Brand Watcher dashboard →]({_DASHBOARD_URL})"
        try:
            from app.services.email_service import get_email_service, markdown_to_html
            svc = get_email_service()
            if not svc.is_available():
                logger.warning("bw digest skipped: email service not configured")
                return False
            # The text/plain alternative must NOT carry markdown syntax — clients
            # that prefer (or preview) the text part would show it literally.
            text_body = re.sub(r"^### (.+)$", r"\1", body_md, flags=re.MULTILINE)
            text_body = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 — \2", text_body)
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
