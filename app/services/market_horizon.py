"""Market Horizon: every rated vendor on a map of scale against momentum.

Not a Magic Quadrant and not a Wave. Both of those carry an analyst's
judgement of vision or strategy, and no reading we collect stands in for
that. What the readings do carry is how big a vendor is (headcount, disclosed
funding, followers, customer evidence) and how fast it is moving (headcount
change, hiring, launches, earned coverage). So those are the two axes, and the
page says so.

Three rules, inherited from the benchmark module this builds on:

- **A vendor is rated only when every required input was measured.** A
  missing funding total is not zero funding, and a vendor nobody read is not
  a vendor that did nothing. The unrated list names the missing reading for
  each vendor, which is also the collection to-do.
- **Every input is a percentile rank among the rated vendors**, not an
  absolute score, because headcount, funding and attention are all skewed.
- **The weights and cut-offs are configuration, printed on the page.** Unlike
  an analyst quadrant, a reader can see every number behind a dot.

Each computation is stored, so the next one can show movement.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services import market_benchmark as mb

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    # The momentum window, in days. Ninety, because a headcount change needs
    # two readings inside it and the profile poll is weekly on most markets.
    "days": 90,
    # Customer evidence is counted over a year: a case study does not stop
    # being evidence after ninety days.
    "customer_days": 365,
    "inputs": {
        "headcount": {"axis": "scale", "weight": 0.35,
                      "label": "LinkedIn headcount (latest fresh reading)"},
        "funding": {"axis": "scale", "weight": 0.30,
                    "label": "Disclosed funding total"},
        "followers": {"axis": "scale", "weight": 0.10,
                      "label": "LinkedIn followers"},
        "customers": {"axis": "scale", "weight": 0.25,
                      "label": "Customer evidence, weighted, last 12 months",
                      "note": "named customer in their own words 3, named in the "
                              "vendor's words 2, unnamed 1"},
        "headcount_pct": {"axis": "momentum", "weight": 0.30,
                          "label": "Headcount change in the period"},
        "jobs_per_head": {"axis": "momentum", "weight": 0.15,
                          "label": "Open roles per 100 staff"},
        "launches": {"axis": "momentum", "weight": 0.25,
                     "label": "Launches and partnerships in the period"},
        "mentions": {"axis": "momentum", "weight": 0.15,
                     "label": "Earned mentions in the period"},
        "posts": {"axis": "momentum", "weight": 0.05,
                  "label": "Own LinkedIn posts in the period"},
        "cb_growth": {"axis": "momentum", "weight": 0.10, "optional": True,
                      "label": "Crunchbase growth score (secondary)"},
    },
    # A vendor at or above the cut on an axis is "high" on it. Fifty is the
    # median of the rated set, so the four tiers start out roughly even.
    "tiers": {"scale_cut": 50, "momentum_cut": 50},
}

TIERS: Dict[str, Dict[str, str]] = {
    "executors": {"label": "Executors",
                  "means": "growing, and already large"},
    "innovators": {"label": "Innovators",
                   "means": "growing fast from a smaller base"},
    "established": {"label": "Established",
                    "means": "large, with little change in the period"},
    "emerging": {"label": "Emerging",
                 "means": "small, and not yet moving"},
}

WHAT_IT_IS_NOT = ("A map of scale against momentum from readings we collect. "
                  "It does not rate product quality, customer satisfaction "
                  "or strategy.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def config_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.getenv("MARKET_HORIZON_CONFIG",
                     os.path.join(here, "config", "market_horizon.json"))


def load_config() -> Dict[str, Any]:
    """The defaults, with anything in ``app/config/market_horizon.json`` laid
    over them. Weights need not sum to one; each axis normalises its own."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                override = json.load(fh)
            for key, value in override.items():
                if key == "inputs" and isinstance(value, dict):
                    for k, v in value.items():
                        cfg["inputs"][k] = {**cfg["inputs"].get(k, {}), **v}
                elif key == "tiers" and isinstance(value, dict):
                    cfg["tiers"].update(value)
                else:
                    cfg[key] = value
        except Exception as exc:  # noqa: BLE001 — a bad file must not hide the map
            logger.warning("market_horizon config unreadable, using defaults: %s", exc)
    return cfg


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _latest_snapshot_value(conn, market_id: int, snapshot_type: str, key: str
                           ) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for bid, val in conn.execute(text(f"""
        SELECT DISTINCT ON (s.brand_id) s.brand_id, (s.data->>:k)::numeric
          FROM bw_vendor_snapshots s
          JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
               AND mb.market_id = :m AND mb.role <> 'excluded'
         WHERE s.market_id = :m AND s.snapshot_type = :t
           AND s.data->>:k IS NOT NULL AND s.data->>:k ~ '^[0-9.]+$'
         ORDER BY s.brand_id, s.observed_at DESC
    """), {"m": market_id, "t": snapshot_type, "k": key}).fetchall():
        out[int(bid)] = float(val)
    return out


def _reviewed_counts(conn, market_id: int, days: int, kinds: Tuple[str, ...]
                     ) -> Dict[int, List[Dict[str, Any]]]:
    """Signal posts of the given kinds per vendor inside the window, one row
    per (vendor, post) whatever the category table says."""
    out: Dict[int, List[Dict[str, Any]]] = {}
    for bid, uri, customer in conn.execute(text("""
        SELECT DISTINCT bac.brand_id, ma.article_uri, ma.review_customer
          FROM bw_market_articles ma
          JOIN bw_article_categories bac ON bac.article_uri = ma.article_uri
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
               AND mb.market_id = ma.market_id AND mb.role <> 'excluded'
          JOIN articles a ON a.uri = ma.article_uri
         WHERE ma.market_id = :m AND ma.review_verdict = 'signal'
           AND LOWER(ma.review_kind) = ANY(:kinds)
           AND COALESCE(a.publication_date, a.submission_date)
               >= (NOW() - (:d || ' days')::interval)::text
    """), {"m": market_id, "d": days, "kinds": list(kinds)}).fetchall():
        out.setdefault(int(bid), []).append(
            {"uri": uri, "customer": customer if isinstance(customer, dict) else None})
    return out


def _customer_weight(reading: Optional[Dict[str, Any]]) -> int:
    if not reading or not (reading.get("name") or "").strip():
        return 1
    return 3 if reading.get("speaker") == "customer" else 2


def gather_inputs(conn, market: Dict[str, Any], cfg: Dict[str, Any]
                  ) -> Tuple[Dict[int, str], Dict[int, Dict[str, float]],
                             Dict[int, Dict[str, str]]]:
    """Every eligible vendor's value for every input, and why any is missing.

    Returns (eligible names, values by vendor, missing reasons by vendor).
    """
    market_id = int(market["id"])
    days = int(cfg.get("days") or 90)
    values: Dict[int, Dict[str, float]] = {}
    missing: Dict[int, Dict[str, str]] = {}

    def put(bid: int, key: str, value: float) -> None:
        values.setdefault(bid, {})[key] = value

    def gap(bid: int, key: str, why: str) -> None:
        missing.setdefault(bid, {})[key] = why

    metrics = {k: mb.metric_values(conn, market, k, days)
               for k in ("headcount", "headcount_pct", "posts", "mentions",
                         "jobs_open", "funding")}
    eligible = metrics["headcount"]["eligible"]

    for key in ("headcount", "headcount_pct", "posts", "mentions", "funding"):
        m = metrics[key]
        for bid in eligible:
            if bid in m["values"]:
                put(bid, key, m["values"][bid])
            else:
                gap(bid, key, m["unmeasured"].get(
                    bid, f"{m['spec']['label'].lower()} not measured"))

    jobs = metrics["jobs_open"]
    for bid in eligible:
        head = values.get(bid, {}).get("headcount")
        if bid not in jobs["values"]:
            gap(bid, "jobs_per_head", jobs["unmeasured"].get(
                bid, "job listings not measured"))
        elif not head:
            gap(bid, "jobs_per_head", "no headcount to divide the open roles by")
        else:
            put(bid, "jobs_per_head", round(jobs["values"][bid] / head * 100, 2))

    followers = _latest_snapshot_value(conn, market_id, "profile", "followers")
    for bid in eligible:
        if bid in followers:
            put(bid, "followers", followers[bid])
        else:
            gap(bid, "followers", "no LinkedIn profile reading with a follower count")

    # Launches, partnerships and customer evidence come from the reviewed
    # posts and matched news. They are measured for a vendor whenever its
    # posts were collected — an absent row is then an observed zero.
    launches = _reviewed_counts(conn, market_id, days,
                                ("launch", "partnership", "product"))
    customers = _reviewed_counts(conn, market_id,
                                 int(cfg.get("customer_days") or 365),
                                 ("customer",))
    for bid in eligible:
        if "posts" in values.get(bid, {}):
            put(bid, "launches", float(len(launches.get(bid, []))))
            put(bid, "customers", float(sum(
                _customer_weight(r["customer"]) for r in customers.get(bid, []))))
        else:
            why = missing.get(bid, {}).get("posts", "posts not collected")
            gap(bid, "launches", why)
            gap(bid, "customers", why)

    growth = _latest_snapshot_value(conn, market_id, "funding", "growth_score")
    for bid in eligible:
        if bid in growth:
            put(bid, "cb_growth", growth[bid])
        else:
            gap(bid, "cb_growth", "no Crunchbase reading")

    return eligible, values, missing


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _percentile(value: float, others: List[float]) -> float:
    """Rank among the others, 0 to 100. Ties share the middle."""
    if not others:
        return 50.0
    below = sum(1 for o in others if o < value)
    ties = sum(1 for o in others if o == value)
    return round((below + 0.5 * ties) / len(others) * 100, 1)


def _tier(scale: float, momentum: float, cuts: Dict[str, Any]) -> str:
    high_scale = scale >= float(cuts.get("scale_cut", 50))
    high_momentum = momentum >= float(cuts.get("momentum_cut", 50))
    if high_scale and high_momentum:
        return "executors"
    if high_momentum:
        return "innovators"
    if high_scale:
        return "established"
    return "emerging"


def compute(conn, market: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
    cfg = cfg or load_config()
    inputs_cfg: Dict[str, Dict[str, Any]] = cfg["inputs"]
    required = [k for k, spec in inputs_cfg.items() if not spec.get("optional")]
    eligible, values, missing = gather_inputs(conn, market, cfg)

    rated_ids = [bid for bid in eligible
                 if all(k in values.get(bid, {}) for k in required)]
    not_rated = []
    for bid in eligible:
        if bid in rated_ids:
            continue
        gaps = [{"key": k, "label": inputs_cfg[k]["label"],
                 "reason": missing.get(bid, {}).get(k, "not measured")}
                for k in required if k not in values.get(bid, {})]
        not_rated.append({"brand_id": bid, "vendor": eligible[bid], "missing": gaps})

    # Percentiles among the rated set only, per input.
    cohort: Dict[str, Dict[int, float]] = {}
    for key in inputs_cfg:
        cohort[key] = {bid: values[bid][key] for bid in rated_ids
                       if key in values.get(bid, {})}

    rated = []
    for bid in rated_ids:
        axes: Dict[str, Dict[str, float]] = {"scale": {"num": 0.0, "den": 0.0},
                                             "momentum": {"num": 0.0, "den": 0.0}}
        detail: Dict[str, Dict[str, Any]] = {}
        for key, spec in inputs_cfg.items():
            if key not in values.get(bid, {}):
                continue
            others = [v for b, v in cohort[key].items() if b != bid]
            pct = _percentile(values[bid][key], others)
            w = float(spec.get("weight") or 0)
            axes[spec["axis"]]["num"] += w * pct
            axes[spec["axis"]]["den"] += w
            detail[key] = {"value": values[bid][key], "percentile": pct,
                           "weight": w, "axis": spec["axis"]}
        scale = round(axes["scale"]["num"] / axes["scale"]["den"], 1) \
            if axes["scale"]["den"] else 50.0
        momentum = round(axes["momentum"]["num"] / axes["momentum"]["den"], 1) \
            if axes["momentum"]["den"] else 50.0
        rated.append({"brand_id": bid, "vendor": eligible[bid],
                      "scale": scale, "momentum": momentum,
                      "tier": _tier(scale, momentum, cfg["tiers"]),
                      "inputs": detail})
    rated.sort(key=lambda r: (-(r["scale"] + r["momentum"]), r["vendor"]))
    not_rated.sort(key=lambda r: (len(r["missing"]), r["vendor"]))

    tier_counts = {t: sum(1 for r in rated if r["tier"] == t) for t in TIERS}
    return {
        "market_id": int(market["id"]),
        "market": market.get("name"),
        "computed_at": _now(),
        "days": int(cfg.get("days") or 90),
        "config": cfg,
        "tiers": {t: {**TIERS[t], "count": tier_counts[t]} for t in TIERS},
        "rated": rated,
        "not_rated": not_rated,
        "counts": {"eligible": len(eligible), "rated": len(rated),
                   "not_rated": len(not_rated)},
        "what_it_is_not": WHAT_IT_IS_NOT,
    }


# ---------------------------------------------------------------------------
# Storage and movement
# ---------------------------------------------------------------------------

def store(conn, result: Dict[str, Any]) -> int:
    row_id = conn.execute(text("""
        INSERT INTO bw_market_horizon (market_id, computed_at, days, config, result)
        VALUES (:m, :at, :d, CAST(:c AS JSONB), CAST(:r AS JSONB))
        RETURNING id
    """), {"m": result["market_id"], "at": result["computed_at"],
           "d": result["days"], "c": json.dumps(result["config"]),
           "r": json.dumps({k: v for k, v in result.items() if k != "config"})}
    ).scalar()
    conn.commit()
    return int(row_id)


def latest(conn, market_id: int, n: int = 2) -> List[Dict[str, Any]]:
    """The most recent stored computations, newest first."""
    out = []
    for row in conn.execute(text("""
        SELECT id, computed_at, days, config, result FROM bw_market_horizon
         WHERE market_id = :m ORDER BY computed_at DESC LIMIT :n
    """), {"m": market_id, "n": n}).mappings().all():
        result = dict(row["result"] or {})
        result["config"] = row["config"]
        result["id"] = row["id"]
        result["computed_at"] = (row["computed_at"].isoformat()
                                 if hasattr(row["computed_at"], "isoformat")
                                 else str(row["computed_at"]))
        out.append(result)
    return out


def with_movement(current: Dict[str, Any], previous: Optional[Dict[str, Any]]
                  ) -> Dict[str, Any]:
    """Each rated vendor's tier and axes last time, so the page can show what
    moved. A vendor rated now and not before is "new"."""
    before = {r["brand_id"]: r for r in (previous or {}).get("rated") or []}
    for r in current.get("rated") or []:
        p = before.get(r["brand_id"])
        r["previous"] = ({"tier": p["tier"], "scale": p["scale"],
                          "momentum": p["momentum"]} if p else None)
        r["moved"] = bool(p and p["tier"] != r["tier"])
    current["previous_at"] = (previous or {}).get("computed_at")
    return current
