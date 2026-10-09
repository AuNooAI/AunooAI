"""The weekly vendor chart: a Top 40 of the market, ranked by momentum.

Each week runs Monday to Sunday, Berlin time. A vendor's place is its
momentum on the Market Maturity Map run that closed the week: the map's
composite of headcount change, open roles, launches and partnerships, earned
mentions, Crunchbase growth and the vendor's own posts over 90 days, each a
percentile among the rated vendors, with weights printed on the map. Ties
break on scale, then name.

The map stores a run a day, so a closed week has a frozen reading already.
The chart still copies its 40 places into ``bw_market_vendor_chart`` when
the week closes: the map's weights and inputs are configuration and will
change, and "weeks at #1" must not change with them. Movement, peak, weeks on
the chart and weeks at #1 are derived from the stored rows when read.
"""

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.services.market_publish import acquired_ids

logger = logging.getLogger(__name__)

CHART_SIZE = 40
# The first run fills this many weeks back, as far as stored map runs go.
# Market 2's runs start on 27 Aug 2026.
BACKFILL_WEEKS = 8

_TZ = ZoneInfo("Europe/Berlin")


DEFAULT_TITLE = "Top {n} Movers"


def title(market: Dict[str, Any], n: int) -> str:
    """The card's name: ``config.chart.title`` with ``{n}`` for the number
    of places, or the default."""
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    tmpl = ((cfg.get("chart") or {}).get("title") or DEFAULT_TITLE)
    return tmpl.replace("{n}", str(n))


def last_frozen_week(today: Optional[date] = None) -> date:
    """The Monday of the newest week that has closed."""
    today = today or datetime.now(_TZ).date()
    ready = today - timedelta(days=7)
    return ready - timedelta(days=ready.weekday())


def _week_bounds(week_start: date):
    start = datetime.combine(week_start, time.min, _TZ)
    return start, start + timedelta(days=7)


def rank_rated(rated: List[Dict[str, Any]], skip: set = frozenset(),
               size: int = CHART_SIZE) -> List[Dict[str, Any]]:
    """The map's rated vendors in chart order."""
    rows = [r for r in rated
            if r.get("brand_id") is not None and r.get("momentum") is not None
            and int(r["brand_id"]) not in skip]
    rows.sort(key=lambda r: (-float(r["momentum"]), -float(r.get("scale") or 0),
                             str(r.get("vendor") or "").lower()))
    return [{"brand_id": int(r["brand_id"]), "vendor": r.get("vendor"),
             "rank": i + 1, "momentum": float(r["momentum"]),
             "scale": r.get("scale"), "band": r.get("band")}
            for i, r in enumerate(rows[:size])]


def compute_week(conn, market_id: int, week_start: date,
                 size: int = CHART_SIZE) -> List[Dict[str, Any]]:
    """Rank the vendors on the newest map run inside the week. Empty when
    the map stored no run that week."""
    start, end = _week_bounds(week_start)
    row = conn.execute(text("""
        SELECT id, result FROM bw_market_horizon
        WHERE market_id = :m AND computed_at >= :start AND computed_at < :end
        ORDER BY computed_at DESC LIMIT 1
    """), {"m": market_id, "start": start, "end": end}).mappings().first()
    if row is None:
        return []
    rows = rank_rated((row["result"] or {}).get("rated") or [],
                      skip=acquired_ids(conn, market_id), size=size)
    return [dict(r, horizon_id=row["id"]) for r in rows]


def store_week(conn, market_id: int, week_start: date,
               rows: List[Dict[str, Any]]) -> int:
    conn.execute(text("""
        DELETE FROM bw_market_vendor_chart
        WHERE market_id = :m AND week_start = :w
    """), {"m": market_id, "w": week_start})
    for r in rows:
        conn.execute(text("""
            INSERT INTO bw_market_vendor_chart
                (market_id, week_start, brand_id, rank, momentum, scale, band,
                 horizon_id)
            VALUES (:m, :w, :b, :rank, :momentum, :scale, :band, :h)
        """), {"m": market_id, "w": week_start, "b": r["brand_id"],
               "rank": r["rank"], "momentum": r["momentum"],
               "scale": r.get("scale"), "band": r.get("band"),
               "h": r.get("horizon_id")})
    conn.commit()
    return len(rows)


def latest_week(conn, market_id: int) -> Optional[date]:
    return conn.execute(text(
        "SELECT MAX(week_start) FROM bw_market_vendor_chart WHERE market_id = :m"
    ), {"m": market_id}).scalar()


def refresh(conn, market_id: int, today: Optional[date] = None) -> List[date]:
    """Freeze every ready week newer than the newest stored one."""
    target = last_frozen_week(today)
    last = latest_week(conn, market_id)
    week = (last + timedelta(days=7) if last
            else target - timedelta(days=7 * (BACKFILL_WEEKS - 1)))
    done = []
    while week <= target:
        rows = compute_week(conn, market_id, week)
        if rows:  # a week with no map run stays off the chart
            store_week(conn, market_id, week, rows)
            done.append(week)
        week += timedelta(days=7)
    return done


def derive(history: Dict[date, Dict[int, int]]) -> List[Dict[str, Any]]:
    """The newest week's places, with movement and runs worked out.

    ``history`` maps each stored week to ``{brand_id: rank}``.
    """
    weeks = sorted(history)
    if not weeks:
        return []
    current, previous = weeks[-1], (weeks[-2] if len(weeks) > 1 else None)
    out = []
    for brand_id, rank in sorted(history[current].items(), key=lambda kv: kv[1]):
        ranks = [history[w][brand_id] for w in weeks if brand_id in history[w]]
        last = history[previous].get(brand_id) if previous else None
        if last is not None:
            move = last - rank
            status = "up" if move > 0 else "down" if move < 0 else "same"
        else:
            move = None
            # On the first stored week every vendor is new; after that a
            # vendor seen before but absent last week has come back.
            status = "reentry" if len(ranks) > 1 else "new"
        out.append({
            "brand_id": brand_id, "rank": rank, "last_week": last,
            "move": move, "status": status, "peak": min(ranks),
            "weeks_on": len(ranks),
            "weeks_at_1": sum(1 for r in ranks if r == 1),
        })
    return out


# What a row says moved the vendor, in reader's words. Own posts and the
# Crunchbase score are left out: a vendor posting more is not news, and the
# Crunchbase score is a second-hand reading.
_DRIVERS = ("launches", "headcount_pct", "jobs_per_head", "mentions")
# Only an input in the top quarter of the rated vendors counts as a driver.
_DRIVER_PERCENTILE = 75.0
_STAGES = {"executors": "Executing", "innovators": "Scaling",
           "established": "Building", "emerging": "Emerging"}
_BANDS = {"accelerating": "Accelerating", "growing": "Growing",
          "holding": "Holding"}


def _driver_text(key: str, value: float) -> Optional[str]:
    n = round(value)
    if key == "launches" and n > 0:
        return f"{n} launch{'es' if n != 1 else ''} and partnerships"
    if key == "headcount_pct" and value > 0:
        return f"headcount +{value:.0f}%"
    if key == "jobs_per_head" and n > 0:
        return f"{n} open role{'s' if n != 1 else ''} per 100 staff"
    if key == "mentions" and n > 0:
        return f"{n} earned mention{'s' if n != 1 else ''}"
    return None


def describe(rated: Dict[str, Any], week_end: date,
             days: int = 90) -> Dict[str, Any]:
    """The map's reading of one vendor, as the card's metadata line: its
    stage and band, the two inputs that most lifted its momentum, and a
    funding round inside the momentum window."""
    inputs = rated.get("inputs") or {}
    ranked = sorted(
        ((k, inputs[k]) for k in _DRIVERS
         if isinstance(inputs.get(k), dict)
         and float(inputs[k].get("percentile") or 0) >= _DRIVER_PERCENTILE),
        key=lambda kv: -float(kv[1].get("percentile") or 0))
    drivers = [t for t in (_driver_text(k, float(v.get("value") or 0))
                           for k, v in ranked) if t][:2]
    funded = None
    f = rated.get("funded") or {}
    try:
        when = date.fromisoformat(str(f.get("date"))[:10]) if f.get("date") else None
    except ValueError:
        when = None
    if when and f.get("round") and week_end - timedelta(days=days) <= when <= week_end:
        funded = f"{f['round']}, {when.strftime('%b %Y')}"
    return {"stage": _STAGES.get(rated.get("tier") or ""),
            "band_label": _BANDS.get(rated.get("band") or ""),
            "drivers": drivers, "funded": funded}


def chart(conn, market_id: int) -> Dict[str, Any]:
    """The newest stored week, ready for the front page card."""
    rows = conn.execute(text("""
        SELECT c.week_start, c.brand_id, c.rank, c.momentum, c.band,
               c.horizon_id, b.display_name AS vendor
        FROM bw_market_vendor_chart c
        JOIN bw_brands b ON b.id = c.brand_id
        WHERE c.market_id = :m
        ORDER BY c.week_start, c.rank
    """), {"m": market_id}).mappings().all()
    if not rows:
        return {"week_start": None, "rows": []}
    history: Dict[date, Dict[int, int]] = {}
    info: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        history.setdefault(r["week_start"], {})[r["brand_id"]] = r["rank"]
        info[r["brand_id"]] = r  # ends on the newest week's row
    week = max(history)
    # The map run the newest week was taken from, for the metadata line.
    horizon_ids = {info[b]["horizon_id"] for b in history[week]
                   if info[b]["horizon_id"] is not None}
    rated: Dict[int, Dict[str, Any]] = {}
    if horizon_ids:
        for (result,) in conn.execute(text(
                "SELECT result FROM bw_market_horizon WHERE id = ANY(:ids)"),
                {"ids": list(horizon_ids)}).fetchall():
            for v in (result or {}).get("rated") or []:
                if v.get("brand_id") is not None:
                    rated[int(v["brand_id"])] = v
    out = []
    for d in derive(history):
        r = info[d["brand_id"]]
        meta = describe(rated.get(d["brand_id"]) or {}, week + timedelta(days=6))
        out.append(dict(d, **meta, vendor=r["vendor"], momentum=r["momentum"],
                        band=r["band"]))
    return {"week_start": week, "rows": out}
