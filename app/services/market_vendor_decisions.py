"""Brand decisions for Market Monitor vendor links.

docs/BRAND_RELEVANCE_MARKET_VENDORS.md. When the market's name match
(market_corpus.attribute_vendors) finds a vendor in an article, the brand
decision (brand_decision.decide: exclusions, ownership, mention, reuse, judge,
headline rule) runs for that article and vendor, and only an earned decision
may write the vendor link. Every decision is stored in brand_article_decisions,
one row per article and vendor.

Off unless MARKET_VENDOR_DECISIONS is set; with it off nothing here is called
and the name match behaves exactly as before.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text

from app.services import brand_decision as bd
from app.services import brand_profile as bp

logger = logging.getLogger(__name__)

TABLE = "brand_article_decisions"
ARTICLE_COLUMNS = ("uri, title, summary, original_title, original_summary, news_source, "
                   "bias_source, topic")


def enabled() -> bool:
    return os.getenv("MARKET_VENDOR_DECISIONS", "").strip().lower() in ("1", "true", "yes", "on")


def retry_cap() -> int:
    try:
        return int(os.getenv("BRAND_RETRY_MAX_ATTEMPTS", "") or 3)
    except ValueError:
        return 3


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def profiles_by_id(conn, brand_ids: Iterable[int]) -> Dict[int, bp.BrandProfile]:
    """Each vendor's brand profile, enabled in Brand Watcher or not: the market
    tracks the vendor either way (panaya tracks four vendors Brand Watcher has
    switched off)."""
    ids = sorted({int(b) for b in brand_ids})
    if not ids:
        return {}
    rows = conn.execute(text("""
        SELECT id, name, display_name, brand_keywords, product_keywords, config, enabled
          FROM bw_brands WHERE id = ANY(:ids)
    """), {"ids": ids}).mappings().all()
    registry: Dict[int, list] = {}
    conn.execute(text("SAVEPOINT mvd_registry"))
    try:
        for r in conn.execute(text("""
            SELECT brand_id, normalized_value FROM bw_vendor_identifiers
             WHERE kind = 'domain' AND valid_to IS NULL AND brand_id = ANY(:ids)
        """), {"ids": ids}).mappings():
            registry.setdefault(int(r["brand_id"]), []).append(r["normalized_value"])
        conn.execute(text("RELEASE SAVEPOINT mvd_registry"))
    except Exception as e:  # noqa: BLE001 - registry absent on most sites
        conn.execute(text("ROLLBACK TO SAVEPOINT mvd_registry"))
        logger.debug("market vendor decisions: no vendor registry (%s)", e)
    return {int(r["id"]): bp.build_profile(dict(r), registry.get(int(r["id"]), ())) for r in rows}


# ---------------------------------------------------------------------------
# Stored decisions and reuse
# ---------------------------------------------------------------------------

def _evidence(v) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v or "{}")
    except (TypeError, ValueError):
        return {}


def stored(conn, uri: str, brand_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(text(f"""
        SELECT outcome, brand_relation, source_relation, judge_version, decision_evidence,
               last_failure, linked
          FROM {TABLE} WHERE article_uri = :u AND brand_id = :b
    """), {"u": uri, "b": int(brand_id)}).mappings().first()
    return dict(row) if row else None


def needs_decision(row: Optional[Dict[str, Any]], profile: bp.BrandProfile) -> bool:
    """Whether a pair should be decided now. A decided pair is settled. An
    unavailable one is retried under the attempt cap. A deferred one waits for
    its profile to change."""
    if row is None:
        return True
    if row["outcome"] == "decided":
        return False
    if row["outcome"] == "unavailable":
        attempts = int((_evidence(row.get("last_failure")) or {}).get("attempts") or 0)
        return attempts < retry_cap()
    return (_evidence(row.get("decision_evidence")) or {}).get("profile_version") != profile.version


def reuse_lookup(conn, uri: str):
    """A ``reuse`` callable for brand_decision.decide that looks in both stores:
    this table and the brand-topic match rows. The input key carries the
    brand, profile, rubric, route, evidence and source relation, so a hit is
    the same judgment."""
    from app.services.brand_decision_store import decision_from_row

    def lookup(key: str) -> Optional[bd.Decision]:
        conn.execute(text("SAVEPOINT mvd_reuse"))
        try:
            row = conn.execute(text(f"""
                SELECT brand_relation, source_relation, judge_version, decision_evidence::text AS evidence
                  FROM {TABLE}
                 WHERE article_uri = :u AND judge_version = :k AND outcome = 'decided'
                UNION ALL
                SELECT brand_relation, source_relation, judge_version, decision_evidence::text
                  FROM keyword_article_matches
                 WHERE article_uri = :u AND judge_version = :k AND brand_relation IS NOT NULL
                   AND COALESCE(relevance_status, '') NOT IN ('relevance_check_failed', 'deferred')
                 LIMIT 1
            """), {"u": uri, "k": key}).mappings().first()
            conn.execute(text("RELEASE SAVEPOINT mvd_reuse"))
            return decision_from_row(dict(row)) if row else None
        except Exception as e:  # noqa: BLE001 - reuse is an optimisation
            conn.execute(text("ROLLBACK TO SAVEPOINT mvd_reuse"))
            logger.debug("market vendor reuse lookup failed for %s: %s", uri[:80], e)
            return None
    return lookup


# ---------------------------------------------------------------------------
# Deciding and saving
# ---------------------------------------------------------------------------

def decide(conn, profile: Optional[bp.BrandProfile], article: Dict[str, Any], *,
           judges=None) -> bd.Decision:
    """The brand decision for one article and one vendor. An article that does
    not verifiably name the vendor is "other": the name match fired on
    something the profile does not accept as the vendor's name."""
    if profile is None:
        return bd.Decision("deferred", provenance="rule", reason="no brand profile for this vendor",
                           evidence={"config_error": "no bw_brands row"})
    from app.services.brand_ingest_hooks import _reserve_judge_call, _settle_budget
    judges = tuple(judges) if judges is not None else bd.configured_judges()
    reserved = _reserve_judge_call()
    if not reserved:
        def over_budget(*_a):
            raise bd.JudgeUnavailable("hourly brand judge budget reached")
        over_budget.route = "budget"
        judges = (over_budget,)
    d = bd.decide(bp.ProfileResolution(profile, brand_topic=False), article, judges=judges,
                  topic_scorer=None, reuse=reuse_lookup(conn, article.get("uri") or ""))
    if reserved:
        _settle_budget(d.model_calls if d is not None else 0)
    return d


def save(conn, uri: str, brand_id: int, market_id: Optional[int], d: bd.Decision, linked: bool,
         previous: Optional[Dict[str, Any]] = None) -> None:
    attempts = int((_evidence((previous or {}).get("last_failure")) or {}).get("attempts") or 0)
    failure = None
    if d.outcome == "unavailable":
        failure = json.dumps({"reason": d.failure, "route": d.route, "attempts": attempts + 1},
                             ensure_ascii=False, default=str)
    evidence = d.to_evidence_json()
    evidence["profile_version"] = evidence.get("profile_version") or ""
    conn.execute(text(f"""
        INSERT INTO {TABLE} (article_uri, brand_id, market_id, outcome, brand_relation, source_relation,
                             judge_version, decision_evidence, last_failure, linked, decided_at)
        VALUES (:u, :b, :m, :o, :r, :s, :k, CAST(:e AS jsonb), CAST(:f AS jsonb), :l, NOW())
        ON CONFLICT (article_uri, brand_id) DO UPDATE SET
            market_id = EXCLUDED.market_id, outcome = EXCLUDED.outcome,
            brand_relation = EXCLUDED.brand_relation, source_relation = EXCLUDED.source_relation,
            judge_version = EXCLUDED.judge_version, decision_evidence = EXCLUDED.decision_evidence,
            last_failure = COALESCE(EXCLUDED.last_failure, {TABLE}.last_failure),
            linked = {TABLE}.linked OR EXCLUDED.linked, decided_at = NOW()
    """), {"u": uri, "b": int(brand_id), "m": market_id, "o": d.outcome, "r": d.brand_relation,
           "s": d.source_relation, "k": d.judge_version or None,
           "e": json.dumps(evidence, ensure_ascii=False, default=str), "f": failure, "l": bool(linked)})


def mark_linked(conn, uri: str, brand_id: int) -> None:
    conn.execute(text(f"UPDATE {TABLE} SET linked = TRUE WHERE article_uri = :u AND brand_id = :b"),
                 {"u": uri, "b": int(brand_id)})


def decide_and_save(conn, market_id: Optional[int], profile: Optional[bp.BrandProfile],
                    brand_id: int, article: Dict[str, Any], *, judges=None) -> bd.Decision:
    """Decide a pair unless a stored decision settles it, save, and return the
    decision the caller links on."""
    from app.services.brand_decision_store import decision_from_row
    uri = article.get("uri") or ""
    prev = stored(conn, uri, brand_id)
    if prev is not None and profile is not None and not needs_decision(prev, profile):
        if prev["outcome"] == "decided":
            d = decision_from_row(dict(prev, evidence=prev.get("decision_evidence")))
            if d is not None:
                return d
        return bd.Decision(prev["outcome"], prev.get("brand_relation"), prev.get("source_relation"),
                           provenance="stored", evidence=_evidence(prev.get("decision_evidence")))
    d = decide(conn, profile, article, judges=judges)
    logger.info("Market vendor decision %s brand=%s: outcome=%s relation=%s source=%s provenance=%s%s",
                uri[:80], brand_id, d.outcome, d.brand_relation, d.source_relation, d.provenance,
                f" failure={d.failure[:160]}" if d.failure else "")
    save(conn, uri, brand_id, market_id, d, linked=False, previous=prev)
    return d


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def retry_unavailable(conn, limit: int = 25, *, judges=None) -> Dict[str, Any]:
    """Re-decide pairs whose judgment was unavailable, under the attempt cap,
    and write the vendor link when the new decision is earned. The article is
    already stored and enriched, so the ingest pipeline is not involved."""
    out = {"selected": 0, "linked": 0, "decided_not_earned": 0, "still_unavailable": 0}
    if not enabled():
        return out
    rows = conn.execute(text(f"""
        SELECT d.article_uri, d.brand_id, d.market_id, d.decision_evidence
          FROM {TABLE} d
         WHERE d.outcome = 'unavailable'
           AND COALESCE((d.last_failure->>'attempts')::int, 0) < :cap
         ORDER BY d.decided_at DESC
         LIMIT :lim
    """), {"cap": retry_cap(), "lim": int(limit)}).mappings().all()
    out["selected"] = len(rows)
    if not rows:
        return out
    from app.services import market_corpus as mcorp
    profiles = profiles_by_id(conn, [r["brand_id"] for r in rows])
    for r in rows:
        art = conn.execute(text(f"SELECT {ARTICLE_COLUMNS} FROM articles WHERE uri = :u"),
                           {"u": r["article_uri"]}).mappings().first()
        if art is None:
            continue
        d = decide_and_save(conn, r["market_id"], profiles.get(int(r["brand_id"])), int(r["brand_id"]),
                            dict(art), judges=judges)
        if d.outcome == "unavailable":
            out["still_unavailable"] += 1
        elif d.earned:
            term = (d.evidence or {}).get("alias") or ""
            mcorp.write_vendor_link(conn, r["article_uri"], int(r["brand_id"]), art["title"] or "",
                                    art["summary"] or "", term)
            mark_linked(conn, r["article_uri"], int(r["brand_id"]))
            out["linked"] += 1
        else:
            out["decided_not_earned"] += 1
    return out
