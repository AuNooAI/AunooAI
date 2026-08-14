"""Customer-defined escalation tiers (see docs/CUSTOMER_ESCALATION_TIERS_SPEC.md).

Severity language in generated prose may only come from a threshold the
customer configured on the brand, evaluated here deterministically — the LLM
just repeats the result. No tiers configured (the default) means no status,
and every surface behaves exactly as before.

Config: bw_brands.config['escalation_tiers'] — ordered list, most severe
last; rules inside a tier are ANDed; the last tier whose rules all pass wins.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Sentiment predicates mirror bw_digest_service so the numbers cited in a
# status match the numbers the digest email shows for the same brand.
_NEG = ("(sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR "
        "sentiment ILIKE '%pessimis%' OR sentiment ILIKE '%critical%' OR "
        "sentiment ILIKE '%alarm%')")
_POS = "(sentiment ILIKE '%positiv%' OR sentiment ILIKE '%optimis%')"

BASELINE_DAYS = 28
DEFAULT_WINDOW_DAYS = 2
MIN_SCORED_FOR_SENTIMENT = 3


def _brand_tiers(conn, brand_id: int) -> List[Dict[str, Any]]:
    row = conn.execute(text(
        "SELECT COALESCE(config, '{}') FROM bw_brands WHERE id = :bid"),
        {"bid": brand_id}).fetchone()
    if not row:
        return []
    cfg = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
    tiers = cfg.get("escalation_tiers") or []
    return [t for t in tiers if isinstance(t, dict)
            and t.get("label") and isinstance(t.get("rules"), dict)]


def _window_metrics(conn, brand_id: int, window_days: int) -> Dict[str, Any]:
    """Volume, baseline, sentiment, and high-risk counts for the brand."""
    row = conn.execute(text(f"""
        SELECT
          COUNT(*) FILTER (WHERE a.submission_date >= (now() - (:w || ' days')::interval)::text) AS win_n,
          COUNT(*) FILTER (WHERE a.submission_date <  (now() - (:w || ' days')::interval)::text
                             AND a.submission_date >= (now() - ((:w + :base) || ' days')::interval)::text) AS base_n,
          COUNT(*) FILTER (WHERE a.submission_date >= (now() - (:w || ' days')::interval)::text
                             AND {_POS}) AS pos,
          COUNT(*) FILTER (WHERE a.submission_date >= (now() - (:w || ' days')::interval)::text
                             AND {_NEG}) AS neg,
          COUNT(*) FILTER (WHERE a.submission_date >= (now() - (:w || ' days')::interval)::text
                             AND COALESCE(a.sentiment, '') <> '') AS scored
        FROM articles a
        JOIN bw_article_categories bac
          ON bac.article_uri = a.uri AND bac.brand_id = :bid
    """), {"bid": brand_id, "w": window_days, "base": BASELINE_DAYS}).fetchone()
    win_n, base_n, pos, neg, scored = (row[0] or 0, row[1] or 0,
                                       row[2] or 0, row[3] or 0, row[4] or 0)
    risks = conn.execute(text("""
        SELECT r.risk_type, COUNT(*) FROM bw_article_risks r
        WHERE r.brand_id = :bid AND r.severity = 'high'
          AND r.detected_at >= now() - (:w || ' days')::interval
        GROUP BY r.risk_type
    """), {"bid": brand_id, "w": window_days}).fetchall()
    # Active issues (Brand Risk v2) for the issue-level rules. Lazy import —
    # brand_risk_assessment calls back into this module for tier evaluation.
    active_issues: list = []
    try:
        from datetime import date
        from app.services.brand_risk_assessment import active_issues_as_of
        active_issues = active_issues_as_of(conn, brand_id, date.today().isoformat())
    except Exception:
        logger.exception("active-issue lookup failed for brand %s", brand_id)
    return {
        "win_daily": win_n / max(window_days, 1),
        "base_daily": base_n / BASELINE_DAYS,
        "net_sentiment": (round(((pos - neg) / scored) * 100)
                          if scored >= MIN_SCORED_FOR_SENTIMENT else None),
        "scored": scored,
        "high_risks": {rt: n for rt, n in risks},
        "active_issues": active_issues,
    }


def _tier_fires(rules: Dict[str, Any], m: Dict[str, Any],
                window_days: int) -> Optional[List[str]]:
    """Reasons the tier fired, or None if any rule fails."""
    reasons: List[str] = []
    if "volume_multiple" in rules:
        mult = float(rules["volume_multiple"])
        if m["base_daily"] <= 0 or m["win_daily"] < mult * m["base_daily"]:
            return None
        reasons.append(
            f"coverage {m['win_daily'] / m['base_daily']:.1f}x baseline over "
            f"{window_days} days ({m['win_daily']:.0f}/day vs {m['base_daily']:.1f}/day)")
    if "net_sentiment_below" in rules:
        if m["net_sentiment"] is None or m["net_sentiment"] > float(rules["net_sentiment_below"]):
            return None
        reasons.append(
            f"net sentiment {m['net_sentiment']} across {m['scored']} scored articles")
    if rules.get("requires_high_risk"):
        if not m["high_risks"]:
            return None
        total = sum(m["high_risks"].values())
        kinds = ", ".join(sorted(m["high_risks"]))
        reasons.append(f"{total} high-severity risk finding(s) ({kinds})")
    if "active_issue_severity" in rules or "active_issue_types" in rules:
        # Brand Risk v2 issue-level rules: fire on an active issue at/above a
        # severity, optionally restricted to listed event types.
        order = {"low": 0, "medium": 1, "high": 2}
        min_sev = order.get(str(rules.get("active_issue_severity", "low")), 0)
        wanted = set(rules.get("active_issue_types") or [])
        hits = [i for i in m.get("active_issues", [])
                if order.get(i["severity"], 0) >= min_sev
                and (not wanted or i["primary_type"] in wanted
                     or wanted.intersection(i.get("secondary_types") or []))]
        if not hits:
            return None
        top = hits[0]
        reasons.append(
            f"active {top['severity']}-severity issue ({top['primary_type']}: "
            f"{top['title'][:80]}, {top['articles']} article(s), "
            f"first seen {top['first_seen']})"
            + (f" and {len(hits) - 1} more" if len(hits) > 1 else ""))
    return reasons or None


def evaluate_brand_tier(conn, brand_id: int) -> Optional[Dict[str, Any]]:
    """The customer-defined status currently in force for a brand, or None.

    {"label": ..., "triggered": [...], "window_days": N} — highest
    (last-listed) tier whose rules all pass. Pure SQL + arithmetic.
    """
    try:
        tiers = _brand_tiers(conn, brand_id)
        if not tiers:
            return None
        result = None
        metrics_by_window: Dict[int, Dict[str, Any]] = {}
        for tier in tiers:  # later entries are more severe; last match wins
            w = int(tier["rules"].get("min_days", DEFAULT_WINDOW_DAYS))
            if w not in metrics_by_window:
                metrics_by_window[w] = _window_metrics(conn, brand_id, w)
            reasons = _tier_fires(tier["rules"], metrics_by_window[w], w)
            if reasons:
                result = {"label": str(tier["label"]),
                          "triggered": reasons, "window_days": w}
        return result
    except Exception:  # noqa: BLE001 — a broken tier config must never break a surface
        logger.exception("escalation tier evaluation failed for brand %s", brand_id)
        return None


def status_prompt_line(status: Optional[Dict[str, Any]]) -> str:
    """The prompt-input line for a fired status; empty string when none."""
    if not status:
        return ""
    return (f'\nCUSTOMER-DEFINED STATUS: "{status["label"]}" — triggered by: '
            + "; ".join(status["triggered"]) + "\n")
