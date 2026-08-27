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
import re
import os
from datetime import datetime, timedelta, timezone
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
    # Innovating is a marker across every tier, not a region of the map: the
    # top third of rated vendors by this score, from what we can read of
    # product work. Patents, code activity and release notes are not held.
    "innovation": {
        "top_fraction": 0.34,
        "inputs": {
            "launches": {"weight": 0.35, "label": "Launches and partnerships in the period"},
            "launches_corroborated": {"weight": 0.25,
                                      "label": "Launches an outside source confirmed"},
            "research": {"weight": 0.20, "label": "Research posts in the period"},
            "engineering_share": {"weight": 0.20,
                                  "label": "Engineering share of open roles"},
        },
    },
    # Two more markers, read the same way as Innovating: a badge on the dot,
    # never a region of the map. Hiring is the top third of the rated set by
    # open roles per 100 staff, with at least a few roles open so a two-person
    # shop with one vacancy does not lead the list. Funded is a round we can
    # date inside the window, from the vendor's own post, a matched news
    # event or the Crunchbase news list.
    "markers": {
        "hiring": {"top_fraction": 0.34, "min_open_roles": 3},
        "funded": {"days": 365},
    },
    # A move of this many points on either axis since the previous map is
    # drawn as a trail from the old position and listed under the map.
    "movement": {"large_shift": 10},
}

STATUSES = ("active", "acquired", "closed")

TIERS: Dict[str, Dict[str, str]] = {
    "executors": {"label": "Executing",
                  "means": "growing, and already large"},
    "innovators": {"label": "Accelerating",
                   "means": "growing fast from a smaller base"},
    "established": {"label": "Establishing",
                    "means": "large, with little change in the period"},
    "emerging": {"label": "Emerging",
                 "means": "small, and not yet moving fast"},
    # Not a region: an acquired vendor is listed, not placed.
    "acquired": {"label": "Acquired",
                 "means": "bought, so no longer rated as an independent vendor"},
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
            put(bid, "jobs_open", float(jobs["values"][bid]))

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

    # Innovation inputs. Research posts follow the posts collection like
    # launches do; corroborated launches are events with more than the
    # vendor's own word behind them; the engineering share needs at least
    # three open roles to mean anything.
    research = _reviewed_counts(conn, market_id, days, ("research",))
    corroborated = _corroborated_launches(conn, market_id, days)
    for bid in eligible:
        if "posts" in values.get(bid, {}):
            put(bid, "research", float(len(research.get(bid, []))))
            put(bid, "launches_corroborated", float(corroborated.get(bid, 0)))
    for bid, share in _engineering_share(conn, market_id).items():
        if share is None:
            gap(bid, "engineering_share", "fewer than three open roles observed")
        else:
            put(bid, "engineering_share", share)

    return eligible, values, missing


def _corroborated_launches(conn, market_id: int, days: int) -> Dict[int, int]:
    """Launch and partnership events with an independent source behind them."""
    return {int(b): int(n) for b, n in conn.execute(text("""
        SELECT ev.brand_id, COUNT(DISTINCT e.id)
          FROM bw_market_events e
          JOIN bw_event_vendors ev ON ev.event_id = e.id
         WHERE e.market_id = :m
           AND e.event_type IN ('product_launch', 'partnership')
           AND COALESCE(e.corroboration, 'vendor_claim')
               NOT IN ('vendor_claim', 'single_source')
           AND COALESCE(e.event_date, e.created_at::date)
               >= (NOW() - (:d || ' days')::interval)::date
         GROUP BY ev.brand_id
    """), {"m": market_id, "d": days}).fetchall()}


def _engineering_share(conn, market_id: int) -> Dict[int, Optional[float]]:
    """Share of a vendor's open roles that are engineering, research or IT,
    as a percentage; None where fewer than three roles were observed."""
    from app.services import market_lists as mlists
    listing = mlists.jobs(conn, market_id, page_size=1, include_all=True)
    totals: Dict[int, int] = {}
    eng: Dict[int, int] = {}
    for row in listing.get("_all") or []:
        if row.get("status") not in ("currently_observed", "newly_observed"):
            continue
        bid = int(row["brand_id"])
        totals[bid] = totals.get(bid, 0) + 1
        if (row.get("function_group") or "") == "engineering":
            eng[bid] = eng.get(bid, 0) + 1
    return {bid: (round(eng.get(bid, 0) / n * 100, 1) if n >= 3 else None)
            for bid, n in totals.items()}


_ROUND_WORDS = re.compile(
    r"\b(pre[- ]seed|seed|series\s+[a-h]|raises?|raised|closes?|secures?|funding round)\b",
    re.IGNORECASE)
_ROUND_NAME = re.compile(r"\b(pre[- ]seed|seed|series\s+[a-h])\b", re.IGNORECASE)


def _round_label(text_: str) -> Optional[str]:
    m = _ROUND_NAME.search(text_ or "")
    if not m:
        return None
    word = re.sub(r"\s+", " ", m.group(1)).lower()
    return word.title() if word.startswith("series") else word.capitalize()


def _funding_rounds(conn, market_id: int, days: int) -> Dict[int, Dict[str, Any]]:
    """The latest dated funding round per vendor inside the window.

    Three readings, in the order we trust them: the vendor's own post the
    reviewer filed as funding, a funding event matched from the news, and
    an item in the vendor's Crunchbase news list whose title reads as a
    round. Whichever is latest wins, and it says where it came from.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    found: Dict[int, Dict[str, Any]] = {}

    def offer(bid: int, date: Optional[str], title: str, source: str,
              round_hint: Optional[str] = None) -> None:
        if not date or date < since:
            return
        label = _round_label(title) or round_hint
        # Latest wins; on the same day, the reading that names the round,
        # then the one that puts an amount on it.
        strength = (2 if label else 0) + (1 if re.search(r"[$€£]\s?\d", title or "") else 0)
        cur = found.get(bid)
        if cur and (cur["date"] > date or (cur["date"] == date and cur["_strength"] >= strength)):
            return
        found[bid] = {"date": date, "round": label, "title": (title or "")[:160],
                      "source": source, "_strength": strength}

    for bid, uri, title, date in conn.execute(text("""
        SELECT DISTINCT bac.brand_id, ma.article_uri, a.title,
               LEFT(COALESCE(a.publication_date, a.submission_date), 10)
          FROM bw_market_articles ma
          JOIN bw_article_categories bac ON bac.article_uri = ma.article_uri
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
               AND mb.market_id = ma.market_id AND mb.role <> 'excluded'
          JOIN articles a ON a.uri = ma.article_uri
         WHERE ma.market_id = :m AND ma.review_verdict = 'signal'
           AND LOWER(ma.review_kind) = 'funding'
    """), {"m": market_id}).fetchall():
        offer(int(bid), date, title or "", "own post")

    for bid, title, date in conn.execute(text("""
        SELECT ev.brand_id, e.title,
               COALESCE(e.event_date, e.published_at::date, e.created_at::date)::text
          FROM bw_market_events e
          JOIN bw_event_vendors ev ON ev.event_id = e.id
         WHERE e.market_id = :m AND e.event_type = 'funding_round'
           AND e.status = 'active'
    """), {"m": market_id}).fetchall():
        offer(int(bid), date, title or "", "news event")

    # The Crunchbase news list carries items about other companies too, so
    # a title counts only when it names this vendor and either names the
    # round or puts a dollar amount on it.
    for bid, name, data in conn.execute(text("""
        SELECT DISTINCT ON (s.brand_id) s.brand_id, b.display_name, s.data
          FROM bw_vendor_snapshots s
          JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
               AND mb.market_id = :m AND mb.role <> 'excluded'
          JOIN bw_brands b ON b.id = s.brand_id
         WHERE s.market_id = :m AND s.snapshot_type = 'funding'
         ORDER BY s.brand_id, s.observed_at DESC
    """), {"m": market_id}).fetchall():
        if not isinstance(data, dict):
            continue
        hint = (data.get("last_funding_type") or "").replace("_", " ").title() or None
        if hint and "unknown" in hint.lower():
            hint = None
        stem = re.sub(r"[^a-z0-9]", "", (name or "").split(" ")[0].lower())
        for item in data.get("recent_news") or []:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            if stem and stem not in re.sub(r"[^a-z0-9]", "", title.lower()):
                continue
            if _ROUND_WORDS.search(title) and (_ROUND_NAME.search(title)
                                               or re.search(r"[$€£]\s?\d", title)):
                offer(int(bid), (item.get("date") or "")[:10], title, "Crunchbase news", hint)
    for f in found.values():
        f.pop("_strength", None)
    return found


def load_controls(conn, market_id: int) -> Dict[int, Dict[str, Any]]:
    """Analyst controls per vendor: multipliers, note, status."""
    out: Dict[int, Dict[str, Any]] = {}
    for r in conn.execute(text("""
        SELECT brand_id, multipliers, note, status, acquired_by, status_date,
               updated_by, updated_at
          FROM bw_market_vendor_controls WHERE market_id = :m
    """), {"m": market_id}).mappings().all():
        out[int(r["brand_id"])] = {
            "multipliers": {k: float(v) for k, v in (r["multipliers"] or {}).items()
                            if isinstance(v, (int, float))},
            "note": r["note"], "status": r["status"] or "active",
            "acquired_by": r["acquired_by"],
            "status_date": r["status_date"].isoformat() if r["status_date"] else None,
            "updated_by": r["updated_by"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
    return out


def save_controls(conn, market_id: int, brand_id: int, *, multipliers: Dict[str, float],
                  note: Optional[str], status: str, acquired_by: Optional[str],
                  status_date: Optional[str], updated_by: Optional[str]) -> Dict[str, Any]:
    clean = {k: max(0.0, min(2.0, float(v))) for k, v in (multipliers or {}).items()
             if k in DEFAULT_CONFIG["inputs"] and isinstance(v, (int, float))}
    clean = {k: v for k, v in clean.items() if v != 1.0}
    conn.execute(text("""
        INSERT INTO bw_market_vendor_controls
            (market_id, brand_id, multipliers, note, status, acquired_by, status_date,
             updated_by, updated_at)
        VALUES (:m, :b, CAST(:mult AS JSONB), :note, :status, :acq, :sd, :by, NOW())
        ON CONFLICT (market_id, brand_id) DO UPDATE SET
            multipliers = EXCLUDED.multipliers, note = EXCLUDED.note,
            status = EXCLUDED.status, acquired_by = EXCLUDED.acquired_by,
            status_date = EXCLUDED.status_date, updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
    """), {"m": market_id, "b": brand_id, "mult": json.dumps(clean),
           "note": (note or "").strip() or None,
           "status": status if status in STATUSES else "active",
           "acq": (acquired_by or "").strip()[:200] or None,
           "sd": status_date or None, "by": updated_by})
    conn.commit()
    return load_controls(conn, market_id).get(brand_id) or {}


def acquisition_hints(conn, market_id: int, days: int = 120) -> List[Dict[str, Any]]:
    """Vendors that look acquired but are not marked so: Crunchbase says
    acquired, or a matched headline in the period says so. A hint, for a
    person to confirm on the vendor page; nothing changes on its own."""
    hints: List[Dict[str, Any]] = []
    for bid, name, by in conn.execute(text("""
        SELECT DISTINCT ON (s.brand_id) s.brand_id, b.display_name, s.data->>'acquired_by'
          FROM bw_vendor_snapshots s
          JOIN bw_brands b ON b.id = s.brand_id
          JOIN bw_market_brands mb ON mb.brand_id = s.brand_id AND mb.market_id = :m
               AND mb.role <> 'excluded'
         WHERE s.market_id = :m AND s.snapshot_type = 'funding'
           AND COALESCE(s.data->>'acquired_by', '') <> ''
         ORDER BY s.brand_id, s.observed_at DESC
    """), {"m": market_id}).fetchall():
        # Crunchbase sometimes stores the acquirer as a JSON object.
        if isinstance(by, str) and by.strip().startswith("{"):
            try:
                by = (json.loads(by) or {}).get("acquirer") or by
            except ValueError:
                pass
        hints.append({"brand_id": int(bid), "vendor": name,
                      "why": f"Crunchbase records it as acquired by {by}"})
    for bid, name, title in conn.execute(text("""
        SELECT DISTINCT ON (bac.brand_id) bac.brand_id, b.display_name, a.title
          FROM bw_article_categories bac
          JOIN articles a ON a.uri = bac.article_uri
          JOIN bw_brands b ON b.id = bac.brand_id
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id AND mb.market_id = :m
               AND mb.role <> 'excluded'
          JOIN bw_market_articles ma ON ma.article_uri = a.uri AND ma.market_id = :m
         WHERE a.title ~* '\\macquir(es|ed|ing|ition)\\M'
           AND a.title ILIKE '%' || b.display_name || '%'
           AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
           AND COALESCE(a.publication_date, a.submission_date)
               >= (NOW() - (:d || ' days')::interval)::text
         ORDER BY bac.brand_id, COALESCE(a.publication_date, a.submission_date) DESC
    """), {"m": market_id, "d": days}).fetchall():
        if not any(h["brand_id"] == int(bid) for h in hints):
            hints.append({"brand_id": int(bid), "vendor": name,
                          "why": f'a headline in the period: "{(title or "")[:120]}"'})
    return hints


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
    controls = load_controls(conn, int(market["id"]))

    # An acquired or closed vendor is listed, not placed, and leaves the
    # cohort every percentile is ranked in.
    # Listed whatever the vendor's role on the market: one excluded after
    # being bought is still an acquisition the reader should see.
    names = {int(r[0]): r[1] for r in conn.execute(text("""
        SELECT mb.brand_id, b.display_name
          FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m
    """), {"m": int(market["id"])}).fetchall()}
    acquired = []
    for bid, ctl in controls.items():
        if bid in names and ctl.get("status") in ("acquired", "closed"):
            acquired.append({"brand_id": bid, "vendor": names[bid],
                             "status": ctl["status"], "acquired_by": ctl.get("acquired_by"),
                             "status_date": ctl.get("status_date"),
                             "note": ctl.get("note")})
    out_of_cohort = {a["brand_id"] for a in acquired}

    rated_ids = [bid for bid in eligible
                 if bid not in out_of_cohort
                 and all(k in values.get(bid, {}) for k in required)]
    not_rated = []
    for bid in eligible:
        if bid in rated_ids or bid in out_of_cohort:
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

    innovation_cfg = (cfg.get("innovation") or {}).get("inputs") or {}
    inno_cohort: Dict[str, Dict[int, float]] = {
        key: {bid: values[bid][key] for bid in rated_ids if key in values.get(bid, {})}
        for key in innovation_cfg}

    rated = []
    for bid in rated_ids:
        ctl = controls.get(bid) or {}
        mult = ctl.get("multipliers") or {}
        axes: Dict[str, Dict[str, float]] = {"scale": {"num": 0.0, "den": 0.0},
                                             "momentum": {"num": 0.0, "den": 0.0}}
        detail: Dict[str, Dict[str, Any]] = {}
        for key, spec in inputs_cfg.items():
            if key not in values.get(bid, {}):
                continue
            others = [v for b, v in cohort[key].items() if b != bid]
            pct = _percentile(values[bid][key], others)
            # The analyst's multiplier scales this vendor's weight on this
            # input; it never touches the value or the percentile.
            w = float(spec.get("weight") or 0) * float(mult.get(key, 1.0))
            axes[spec["axis"]]["num"] += w * pct
            axes[spec["axis"]]["den"] += w
            detail[key] = {"value": values[bid][key], "percentile": pct,
                           "weight": round(w, 3), "axis": spec["axis"],
                           **({"multiplier": mult[key]} if key in mult else {})}
        # Innovation: a score beside the axes, from the product-work inputs.
        inum = iden = 0.0
        inno_detail: Dict[str, Dict[str, Any]] = {}
        for key, spec in innovation_cfg.items():
            if key not in values.get(bid, {}):
                continue
            others = [v for b, v in inno_cohort[key].items() if b != bid]
            pct = _percentile(values[bid][key], others)
            w = float(spec.get("weight") or 0)
            inum += w * pct
            iden += w
            inno_detail[key] = {"value": values[bid][key], "percentile": pct, "weight": w}
        scale = round(axes["scale"]["num"] / axes["scale"]["den"], 1) \
            if axes["scale"]["den"] else 50.0
        momentum = round(axes["momentum"]["num"] / axes["momentum"]["den"], 1) \
            if axes["momentum"]["den"] else 50.0
        rated.append({"brand_id": bid, "vendor": eligible[bid],
                      "scale": scale, "momentum": momentum,
                      "tier": _tier(scale, momentum, cfg["tiers"]),
                      "inputs": detail,
                      "innovation": round(inum / iden, 1) if iden else None,
                      "innovation_inputs": inno_detail,
                      "innovating": False,
                      "hiring": False, "hiring_detail": None, "funded": None,
                      "analyst_note": ctl.get("note"),
                      "multipliers": mult or None})
    # The Innovating marker: the top third by innovation score, and only
    # vendors that shipped something — a high rank among zeros is not a rank.
    top_fraction = float((cfg.get("innovation") or {}).get("top_fraction") or 0.34)
    scored = sorted((r for r in rated if r["innovation"] is not None
                     and (r["inputs"].get("launches") or {}).get("value", 0) > 0),
                    key=lambda r: -r["innovation"])
    import math
    for r in scored[:int(math.ceil(len(rated) * top_fraction))]:
        r["innovating"] = True

    # Hiring and Funded are read for every vendor still in the cohort, rated
    # or not: a seed round is worth listing even when the vendor has no
    # disclosed total to be rated on. The bar for Hiring is set by the rated
    # set, so the not-rated vendors are measured against the same ruler.
    markers_cfg = cfg.get("markers") or {}
    hiring_cfg = markers_cfg.get("hiring") or {}
    min_roles = float(hiring_cfg.get("min_open_roles") or 3)
    ratios = sorted((values[b]["jobs_per_head"] for b in rated_ids
                     if "jobs_per_head" in values.get(b, {})
                     and values[b].get("jobs_open", 0) >= min_roles), reverse=True)
    top_n = int(math.ceil(len(ratios) * float(hiring_cfg.get("top_fraction") or 0.34)))
    hiring_bar = ratios[top_n - 1] if top_n and ratios else None
    rounds = _funding_rounds(conn, int(market["id"]),
                             int((markers_cfg.get("funded") or {}).get("days") or 365))
    rated_by_id = {r["brand_id"]: r for r in rated}
    hiring_list, funded_list = [], []
    for bid, name in eligible.items():
        if bid in out_of_cohort:
            continue
        v = values.get(bid, {})
        is_hiring = (hiring_bar is not None and "jobs_per_head" in v
                     and v.get("jobs_open", 0) >= min_roles and v["jobs_per_head"] >= hiring_bar)
        hiring_detail = ({"open_roles": int(v["jobs_open"]), "per_100": v["jobs_per_head"]}
                         if is_hiring else None)
        funded = rounds.get(bid)
        if bid in rated_by_id:
            rated_by_id[bid]["hiring"] = is_hiring
            rated_by_id[bid]["hiring_detail"] = hiring_detail
            rated_by_id[bid]["funded"] = funded
        if is_hiring:
            hiring_list.append({"brand_id": bid, "vendor": name, "rated": bid in rated_by_id,
                                **hiring_detail})
        if funded:
            funded_list.append({"brand_id": bid, "vendor": name, "rated": bid in rated_by_id,
                                **funded})
    hiring_list.sort(key=lambda h: (-h["per_100"], h["vendor"]))
    funded_list.sort(key=lambda f: (f["date"], f["vendor"]), reverse=True)
    rated.sort(key=lambda r: (-(r["scale"] + r["momentum"]), r["vendor"]))
    not_rated.sort(key=lambda r: (len(r["missing"]), r["vendor"]))
    acquired.sort(key=lambda a: a["vendor"])

    tier_counts = {t: sum(1 for r in rated if r["tier"] == t) for t in TIERS}
    tier_counts["acquired"] = len(acquired)
    try:
        hints = [h for h in acquisition_hints(conn, int(market["id"]))
                 if h["brand_id"] not in out_of_cohort]
    except Exception as exc:  # noqa: BLE001 — hints are a convenience
        logger.warning("acquisition hints failed: %s", exc)
        hints = []
    return {
        "market_id": int(market["id"]),
        "market": market.get("name"),
        "computed_at": _now(),
        "days": int(cfg.get("days") or 90),
        "config": cfg,
        "tiers": {t: {**TIERS[t], "count": tier_counts[t]} for t in TIERS},
        "rated": rated,
        "not_rated": not_rated,
        "acquired": acquired,
        "innovating": [r["vendor"] for r in rated if r["innovating"]],
        "markers": {"hiring": hiring_list, "funded": funded_list,
                    "hiring_bar": hiring_bar, "min_open_roles": int(min_roles),
                    "funded_days": int((markers_cfg.get("funded") or {}).get("days") or 365)},
        "acquisition_hints": hints,
        "counts": {"eligible": len(eligible), "rated": len(rated),
                   "not_rated": len(not_rated), "acquired": len(acquired),
                   "innovating": sum(1 for r in rated if r["innovating"]),
                   "hiring": len(hiring_list), "funded": len(funded_list)},
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
        # Tier names are presentation, so a stored map takes the current
        # ones rather than the ones in force when it was computed.
        for key, info in (result.get("tiers") or {}).items():
            if key in TIERS and isinstance(info, dict):
                info.update({k: v for k, v in TIERS[key].items()})
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
    large = float(((current.get("config") or {}).get("movement") or {}).get("large_shift") or 10)
    moves = []
    for r in current.get("rated") or []:
        p = before.get(r["brand_id"])
        r["previous"] = ({"tier": p["tier"], "scale": p["scale"],
                          "momentum": p["momentum"]} if p else None)
        r["moved"] = bool(p and p["tier"] != r["tier"])
        r["shift"] = None
        r["big_move"] = False
        if p:
            ds = round(float(r["scale"]) - float(p["scale"]), 1)
            dm = round(float(r["momentum"]) - float(p["momentum"]), 1)
            r["shift"] = {"scale": ds, "momentum": dm}
            if abs(ds) >= large or abs(dm) >= large:
                r["big_move"] = True
                moves.append({"brand_id": r["brand_id"], "vendor": r["vendor"],
                              "scale": ds, "momentum": dm, "tier": r["tier"],
                              "previous_tier": p["tier"]})
    moves.sort(key=lambda m: -(abs(m["scale"]) + abs(m["momentum"])))
    current["previous_at"] = (previous or {}).get("computed_at")
    current["moves"] = moves
    current["large_shift"] = large
    return current
