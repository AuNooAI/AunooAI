"""Market Monitor API — markets, registry import, vendors, collection health.

Monolith port. Mounted through the module registry as ``market_monitor``, so
the whole feature can be switched off from the Explore gear icon and its routes
404 rather than 403 — an unfinished market should not be advertised.

**Route order matters.** ``/markets/import/validate`` is declared before
``/markets/{market_id}``. FastAPI matches in declaration order, and with the
dynamic route first "import" is parsed as a market id and the request dies at
422 before reaching a handler.

Every handler that touches the database does so on a thread. The connection
facade is synchronous, and an 83-row import held on the event loop blocks every
other request in the process — the failure mode is a 504 on unrelated pages,
not a slow import.

The Bright Data callback lives here too but declares no ``verify_session``:
a provider has no session to present. It authenticates on the shared secret the
provider echoes back, and finds its market from the run row.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import get_database_instance
from app.security.session import verify_session, verify_session_optional
from app.services import market_collect as mc
from app.services import market_publish as mp
from app.services import market_import as mi

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-monitor", tags=["Market Monitor"])

# 10 MB. The SOC Automation workbook is 36 KB; anything three orders of
# magnitude larger is not a vendor registry.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

KNOWN_SOURCES = {
    "linkedin_company_post", "linkedin_company_profile",
    "crunchbase_company", "linkedin_jobs",
    "vendor_web", "vendor_web_discovery",
}

# Sources that spend money at Bright Data. Gated on BRIGHTDATA_LINKEDIN_ENABLED
# and billed per record, unlike the internal fetchers.
PAID_SOURCES = {
    "linkedin_company_post", "linkedin_company_profile",
    "crunchbase_company", "linkedin_jobs",
}


def _conn():
    return get_database_instance()._temp_get_connection()


def _slugify(value: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s[:100] or "market"


def _load_market(conn, market_id: int) -> Dict[str, Any]:
    row = conn.execute(text("""
        SELECT id, name, slug, question, description, ontology, config,
               enabled, is_public, created_at, updated_at
        FROM bw_markets WHERE id = :m
    """), {"m": market_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Market not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MarketCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    question: Optional[str] = None
    description: Optional[str] = None
    ontology: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


class MarketUpdate(BaseModel):
    name: Optional[str] = None
    question: Optional[str] = None
    description: Optional[str] = None
    ontology: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    is_public: Optional[bool] = None


class VendorFilter(BaseModel):
    """Rule for selecting vendors out of a market registry.

    Reads the ``baseline`` block the importer wrote, so the same spreadsheet
    columns an analyst reasoned about are the ones a rule can act on. Fields are
    ANDed; values within a field are ORed. An empty filter matches nothing — a
    toggle that silently means "all 82" is how a bill gets a surprise in it.
    """

    funding_status: Optional[List[str]] = None
    countries: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    sub_categories: Optional[List[str]] = None
    roles: Optional[List[str]] = None
    min_headcount: Optional[int] = None
    max_headcount: Optional[int] = None
    min_founded_year: Optional[int] = None
    max_founded_year: Optional[int] = None
    min_funding_musd: Optional[float] = None
    has_linkedin: Optional[bool] = None
    brand_ids: Optional[List[int]] = None


class VendorCollectionToggle(BaseModel):
    enabled: bool
    filter: VendorFilter = Field(default_factory=VendorFilter)
    # Which switch to throw. ``collection`` is whether we spend on watching a
    # vendor; ``brand_monitoring`` is whether it appears in Brand Watcher as a
    # brand in its own right. They are independent — a vendor can be collected
    # for the market without being a brand, which is the default.
    field: str = Field("collection", pattern="^(collection|brand_monitoring)$")
    # Preview by default: a bulk toggle over a registry should be confirmed,
    # not fired by accident.
    dry_run: bool = True


class VendorVisibility(BaseModel):
    brand_ids: List[int]
    is_public: bool


class ReviewTaskUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved|dismissed)$")
    resolution: Dict[str, Any] = Field(default_factory=dict)


class ManualRun(BaseModel):
    source: str = Field(..., min_length=1, max_length=64)


def _refresh_brand_keywords(conn, brand_ids: List[int]) -> int:
    """Rewrite brand keywords for vendors joining Brand Watcher.

    The importer stores the workbook's names verbatim, which is right for a
    registry and wrong for a classifier. ``brand_keywords_for_vendor`` adds a
    qualifier to the names that are ordinary English words, so "Variance"
    becomes "Variance security" and stops matching statistics articles.

    Existing aliases are preserved by reading them back out of the row: an
    operator may have added a former name or a ticker by hand, and this must
    not throw that away.
    """
    rows = conn.execute(text("""
        SELECT b.id, b.display_name, b.brand_keywords
        FROM bw_brands b WHERE b.id = ANY(:ids)
    """), {"ids": brand_ids}).fetchall()

    changed = 0
    for brand_id, display_name, existing in rows:
        current = existing if isinstance(existing, list) else []
        # Drop the bare form of the display name; keep everything else as an
        # alias so hand-added entries survive.
        base = display_name.split("(")[0].strip()
        aliases = [k for k in current
                   if k and k.strip().lower() != base.lower()]
        wanted = mc.brand_keywords_for_vendor(display_name, aliases)
        if wanted and wanted != current:
            conn.execute(text("""
                UPDATE bw_brands
                SET brand_keywords = CAST(:kw AS JSONB), updated_at = NOW()
                WHERE id = :id
            """), {"kw": json.dumps(wanted), "id": brand_id})
            changed += 1
    return changed


def _filter_sql(f: VendorFilter):
    """Turn a VendorFilter into a WHERE fragment over ``bw_market_brands mb``.

    Returns ``("", {})`` when nothing was specified, which callers treat as
    "matches nothing" rather than "matches everything".
    """
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if f.brand_ids:
        clauses.append("mb.brand_id = ANY(:f_ids)")
        params["f_ids"] = f.brand_ids
    if f.roles:
        clauses.append("mb.role = ANY(:f_roles)")
        params["f_roles"] = f.roles
    if f.funding_status:
        clauses.append("mb.baseline->'funding_baseline'->>'status' = ANY(:f_fund)")
        params["f_fund"] = f.funding_status
    if f.countries:
        clauses.append("mb.baseline->>'hq_country' = ANY(:f_country)")
        params["f_country"] = f.countries
    if f.categories:
        clauses.append("mb.baseline->'taxonomy'->>'category' = ANY(:f_cat)")
        params["f_cat"] = f.categories
    if f.sub_categories:
        clauses.append("mb.baseline->'taxonomy'->>'sub_category' = ANY(:f_sub)")
        params["f_sub"] = f.sub_categories
    # A NULL stays NULL and drops out of the comparison, which is what we want:
    # "headcount at least 50" must not sweep in vendors whose headcount we
    # never learned.
    if f.min_headcount is not None:
        clauses.append("(mb.baseline->'metrics'->>'employee_count')::numeric >= :f_hc_min")
        params["f_hc_min"] = f.min_headcount
    if f.max_headcount is not None:
        clauses.append("(mb.baseline->'metrics'->>'employee_count')::numeric <= :f_hc_max")
        params["f_hc_max"] = f.max_headcount
    if f.min_founded_year is not None:
        clauses.append("(mb.baseline->>'founded_year')::numeric >= :f_fy_min")
        params["f_fy_min"] = f.min_founded_year
    if f.max_founded_year is not None:
        clauses.append("(mb.baseline->>'founded_year')::numeric <= :f_fy_max")
        params["f_fy_max"] = f.max_founded_year
    if f.min_funding_musd is not None:
        clauses.append("(mb.baseline->'funding_baseline'->>'total_musd')::numeric >= :f_amt")
        params["f_amt"] = f.min_funding_musd
    if f.has_linkedin is not None:
        exists = ("EXISTS (SELECT 1 FROM bw_vendor_identifiers i "
                  "WHERE i.brand_id = mb.brand_id AND i.valid_to IS NULL "
                  "AND i.kind = 'linkedin_company_url')")
        clauses.append(exists if f.has_linkedin else f"NOT {exists}")

    if not clauses:
        return "", {}
    return " AND ".join(clauses), params


# ---------------------------------------------------------------------------
# Import — static paths declared before /markets/{market_id}
# ---------------------------------------------------------------------------

async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    return data


@router.post("/markets/import/validate")
async def validate_import(
    file: UploadFile = File(...),
    session=Depends(verify_session),
):
    """Parse a registry workbook and report exactly what an import would do.

    Writes nothing. The returned ``batch_id`` is derived from the file's bytes
    and the mapping version, so committing a different file — or the same file
    after the mapping rules changed — is rejected rather than silently applied.
    """
    data = await _read_upload(file)
    parsed = await asyncio.to_thread(mi.parse_workbook, data)
    return mi.build_report(parsed)


@router.post("/markets/import/commit")
async def commit_import(
    file: UploadFile = File(...),
    market_id: int = Form(...),
    batch_id: str = Form(...),
    allow_partial: bool = Form(False),
    session=Depends(verify_session),
):
    """Apply a validated workbook to a market, in one transaction.

    The file is re-sent rather than cached server-side: the ``batch_id`` an
    operator approved is a hash of the bytes, so re-deriving it here proves they
    are committing the registry they actually reviewed.
    """
    data = await _read_upload(file)
    parsed = await asyncio.to_thread(mi.parse_workbook, data)
    if parsed.batch_id != batch_id:
        raise HTTPException(
            status_code=409,
            detail="This file does not match the validated batch. Re-run "
                   "validation and review the report before committing.",
        )
    report = mi.build_report(parsed)
    if not report["ok"] and not allow_partial:
        raise HTTPException(status_code=422, detail=report)

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            result = mi.commit_import(conn, market_id=market_id, parsed=parsed)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        result = await asyncio.to_thread(_work)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Market import failed for market %s", market_id)
        raise HTTPException(
            status_code=500, detail=f"Import failed and was rolled back: {e}"
        )
    result["report"] = report["counts"]
    return result


# ---------------------------------------------------------------------------
# Market CRUD
# ---------------------------------------------------------------------------

@router.get("/markets")
async def list_markets(session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            rows = conn.execute(text("""
                SELECT m.id, m.name, m.slug, m.question, m.description,
                       m.enabled, m.is_public, m.created_at, m.updated_at,
                       COUNT(mb.id) FILTER (WHERE mb.role <> 'excluded') AS vendors,
                       COUNT(mb.id) FILTER (WHERE mb.collection_enabled
                                            AND mb.role <> 'excluded') AS collecting,
                       COUNT(mb.id) FILTER (WHERE mb.is_public) AS public_vendors
                FROM bw_markets m
                LEFT JOIN bw_market_brands mb ON mb.market_id = m.id
                GROUP BY m.id ORDER BY m.name
            """)).mappings().all()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.post("/markets", status_code=201)
async def create_market(payload: MarketCreate, session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            market_id = conn.execute(text("""
                INSERT INTO bw_markets (name, slug, question, description,
                                        ontology, config)
                VALUES (:n, :s, :q, :d, CAST(:o AS JSONB), CAST(:c AS JSONB))
                RETURNING id
            """), {"n": payload.name, "s": _slugify(payload.name),
                   "q": payload.question, "d": payload.description,
                   "o": json.dumps(payload.ontology),
                   "c": json.dumps(payload.config)}).scalar()
            conn.commit()
            return _load_market(conn, market_id)
        except Exception as e:
            conn.rollback()
            if "bw_markets_slug_key" in str(e):
                raise HTTPException(409, "A market with that name exists")
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}")
async def get_market(market_id: int, session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            counts = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE role = 'vendor') AS vendors,
                       COUNT(*) FILTER (WHERE role = 'excluded') AS excluded,
                       COUNT(*) FILTER (WHERE collection_enabled
                                        AND role <> 'excluded') AS collecting,
                       COUNT(*) FILTER (WHERE is_public) AS public_vendors
                FROM bw_market_brands WHERE market_id = :m
            """), {"m": market_id}).mappings().first()
            market["counts"] = dict(counts or {})
            market["open_review_tasks"] = conn.execute(text(
                "SELECT COUNT(*) FROM bw_review_tasks "
                "WHERE market_id = :m AND status = 'open'"
            ), {"m": market_id}).scalar() or 0
            return market
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.put("/markets/{market_id}")
async def update_market(market_id: int, payload: MarketUpdate,
                        session=Depends(verify_session)):
    fields = payload.model_dump(exclude_none=True)

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            if not fields:
                return _load_market(conn, market_id)
            sets, params = [], {"m": market_id}
            for key in ("name", "question", "description", "enabled", "is_public"):
                if key in fields:
                    sets.append(f"{key} = :{key}")
                    params[key] = fields[key]
            for key in ("ontology", "config"):
                if key in fields:
                    sets.append(f"{key} = CAST(:{key} AS JSONB)")
                    params[key] = json.dumps(fields[key])
            conn.execute(text(
                f"UPDATE bw_markets SET {', '.join(sets)}, updated_at = NOW() "
                "WHERE id = :m"), params)
            conn.commit()
            return _load_market(conn, market_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.delete("/markets/{market_id}")
async def delete_market(market_id: int, session=Depends(verify_session)):
    """Delete the market. Vendor brands survive.

    Cascading into ``bw_brands`` would destroy monitoring configuration and
    every article attribution built on it. The membership rows go; the brands
    stay and can be re-imported or reassigned.
    """
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            conn.execute(text("DELETE FROM bw_markets WHERE id = :m"), {"m": market_id})
            conn.commit()
            return {"ok": True, "deleted": market_id}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

@router.get("/markets/{market_id}/vendors")
async def list_vendors(
    market_id: int,
    role: Optional[str] = Query(None, pattern="^(vendor|watch|excluded)$"),
    collecting_only: bool = Query(False),
    session=Depends(verify_session),
):
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            sql = """SELECT mb.brand_id, mb.role, mb.sort_order, mb.is_public,
                            mb.collection_enabled, mb.review_status, mb.baseline,
                            b.name AS slug, b.display_name, b.enabled,
                            (SELECT json_agg(json_build_object(
                                 'kind', i.kind, 'value', i.display_value,
                                 'normalized', i.normalized_value))
                             FROM bw_vendor_identifiers i
                             WHERE i.brand_id = b.id AND i.valid_to IS NULL)
                                AS identifiers
                     FROM bw_market_brands mb
                     JOIN bw_brands b ON b.id = mb.brand_id
                     WHERE mb.market_id = :m"""
            params: Dict[str, Any] = {"m": market_id}
            if role:
                sql += " AND mb.role = :r"
                params["r"] = role
            if collecting_only:
                sql += " AND mb.collection_enabled"
            sql += " ORDER BY mb.sort_order, b.display_name"
            return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.post("/markets/{market_id}/vendors/collection")
async def set_vendor_collection(market_id: int, payload: VendorCollectionToggle,
                                session=Depends(verify_session)):
    """Turn collection, or brand monitoring, on or off for selected vendors.

    The motivating case is narrowing a large registry to the vendors worth
    paying to follow — "only collect for funded vendors" is
    ``{"funding_status": ["Disclosed"]}``. Defaults to a dry run: the response
    lists exactly which vendors would change before anything does.

    ``field="brand_monitoring"`` throws the other switch. Turning it on also
    rewrites that vendor's ``brand_keywords`` through
    ``brand_keywords_for_vendor``, because the names the importer stored are
    raw and some of them are ordinary words — an unqualified "Variance" matched
    13 analysed articles here, none of them about the company.
    """
    where, params = _filter_sql(payload.filter)
    if not where:
        raise HTTPException(
            status_code=400,
            detail="Specify at least one filter field or an explicit brand_ids "
                   "list. An empty rule is not treated as 'all vendors'.",
        )
    if not payload.filter.roles:
        # A rule about funding or headcount says nothing about scope. Without
        # this, "collect for every funded vendor" also switches on the rows an
        # analyst marked out of scope — Edge Delta is funded and excluded. Ask
        # for them by naming the role.
        where += " AND mb.role <> 'excluded'"

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            p = dict(params)
            p["m"] = market_id
            column = ("collection_enabled" if payload.field == "collection"
                      else "brand_monitoring_enabled")
            selected = [dict(r) for r in conn.execute(text(f"""
                SELECT mb.brand_id, b.display_name, mb.role,
                       mb.{column} AS current_value
                FROM bw_market_brands mb
                JOIN bw_brands b ON b.id = mb.brand_id
                WHERE mb.market_id = :m AND {where}
                ORDER BY b.display_name
            """), p).mappings().all()]
            changing = [r for r in selected
                        if r["current_value"] != payload.enabled]

            if payload.dry_run:
                return {
                    "dry_run": True, "enabled": payload.enabled,
                    "field": payload.field,
                    "matched": len(selected), "would_change": len(changing),
                    "vendors": [{"brand_id": r["brand_id"],
                                 "name": r["display_name"],
                                 "currently": r["current_value"]}
                                for r in selected],
                }

            ids = [r["brand_id"] for r in changing]
            if not ids:
                return {"dry_run": False, "enabled": payload.enabled,
                        "field": payload.field,
                        "matched": len(selected), "changed": 0}
            conn.execute(text(f"""
                UPDATE bw_market_brands
                SET {column} = :target, updated_at = NOW()
                WHERE market_id = :m AND brand_id = ANY(:ids)
            """), {"target": payload.enabled, "m": market_id, "ids": ids})

            keywords_fixed = 0
            if payload.field == "brand_monitoring":
                # bw_brands.enabled is the gate Brand Watcher already reads
                # everywhere — classification, the dashboard, the alert config.
                # Driving it from here means the toggle works with no changes
                # to that code, and "enabled" keeps meaning what it says.
                # Market collection does not read it, so a vendor switched off
                # as a brand is still collected for the market.
                conn.execute(text("""
                    UPDATE bw_brands SET enabled = :target, updated_at = NOW()
                    WHERE id = ANY(:ids)
                """), {"target": payload.enabled, "ids": ids})
                if payload.enabled:
                    keywords_fixed = _refresh_brand_keywords(conn, ids)
            conn.commit()
            return {"dry_run": False, "enabled": payload.enabled,
                    "field": payload.field,
                    "keywords_rewritten": keywords_fixed,
                    "matched": len(selected), "changed": len(ids),
                    "vendors": [{"brand_id": r["brand_id"],
                                 "name": r["display_name"]} for r in changing]}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/vendors/facets")
async def vendor_facets(market_id: int, session=Depends(verify_session)):
    """The distinct values a vendor filter can be built from, with counts.

    So the toggle UI offers the funding statuses and countries this registry
    actually contains, rather than a hardcoded list that drifts from the data.
    """
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            out: Dict[str, Any] = {}
            for name, expr in (
                ("funding_status", "mb.baseline->'funding_baseline'->>'status'"),
                ("countries", "mb.baseline->>'hq_country'"),
                ("categories", "mb.baseline->'taxonomy'->>'category'"),
                ("sub_categories", "mb.baseline->'taxonomy'->>'sub_category'"),
                ("roles", "mb.role"),
            ):
                rows = conn.execute(text(
                    f"SELECT {expr} AS value, COUNT(*) AS n "
                    "FROM bw_market_brands mb WHERE mb.market_id = :m "
                    f"AND {expr} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1"
                ), {"m": market_id}).mappings().all()
                out[name] = [dict(r) for r in rows]
            totals = conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE collection_enabled) AS collecting,
                       COUNT(*) FILTER (WHERE is_public) AS public
                FROM bw_market_brands WHERE market_id = :m
            """), {"m": market_id}).mappings().first()
            out["totals"] = dict(totals or {})
            return out
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.put("/markets/{market_id}/vendors/visibility")
async def set_vendor_visibility(market_id: int, payload: VendorVisibility,
                                session=Depends(verify_session)):
    """Opt named vendors into or out of a public surface.

    Tracking a vendor and publishing a page about it are separate decisions, so
    they are separate flags rather than one.
    """
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            if not payload.brand_ids:
                return {"updated": 0}
            result = conn.execute(text("""
                UPDATE bw_market_brands SET is_public = :p, updated_at = NOW()
                WHERE market_id = :m AND brand_id = ANY(:ids)
            """), {"p": payload.is_public, "m": market_id,
                   "ids": payload.brand_ids})
            conn.commit()
            return {"updated": result.rowcount or 0, "is_public": payload.is_public}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@router.get("/markets/{market_id}/review-tasks")
async def list_review_tasks(
    market_id: int,
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    session=Depends(verify_session),
):
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            sql = """SELECT t.id, t.brand_id, t.kind, t.severity, t.status,
                            t.field, t.message, t.source_ref, t.resolution,
                            t.created_at, t.updated_at, t.resolved_at,
                            b.display_name AS vendor
                     FROM bw_review_tasks t
                     LEFT JOIN bw_brands b ON b.id = t.brand_id
                     WHERE t.market_id = :m"""
            params: Dict[str, Any] = {"m": market_id, "lim": limit}
            if status:
                sql += " AND t.status = :s"
                params["s"] = status
            if severity:
                sql += " AND t.severity = :sev"
                params["sev"] = severity
            sql += (" ORDER BY CASE t.severity WHEN 'high' THEN 0 "
                    "WHEN 'medium' THEN 1 ELSE 2 END, t.id LIMIT :lim")
            return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.put("/markets/{market_id}/review-tasks/{task_id}")
async def update_review_task(market_id: int, task_id: int,
                             payload: ReviewTaskUpdate,
                             session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            result = conn.execute(text("""
                UPDATE bw_review_tasks
                SET status = :s, resolution = CAST(:r AS JSONB),
                    resolved_at = CASE WHEN :s IN ('resolved','dismissed')
                                       THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE id = :id AND market_id = :m
            """), {"s": payload.status, "r": json.dumps(payload.resolution),
                   "id": task_id, "m": market_id})
            if not result.rowcount:
                conn.rollback()
                raise HTTPException(404, "Review task not found")
            conn.commit()
            return {"ok": True, "id": task_id, "status": payload.status}
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------


class CollectionSetup(BaseModel):
    # Appended to vendor names too short or too ordinary to search alone. The
    # firehose collector reads a two-word keyword as AND-of-words.
    qualifier: str = Field("security", min_length=2, max_length=40)
    # none | funded | all. Funded by default: a disclosed raise is the best
    # available proxy for a vendor active enough to generate coverage, and
    # searching all 82 spends quota on companies nobody writes about.
    vendor_names: str = Field("funded", pattern="^(none|funded|all)$")
    # Preview by default. Creating the group starts spending provider quota on
    # the next collection cycle.
    dry_run: bool = True


class CollectionTerms(BaseModel):
    """The market's own search language — what the category is called."""

    terms: List[str] = Field(default_factory=list, max_length=60)


@router.put("/markets/{market_id}/collection-terms")
async def set_collection_terms(market_id: int, payload: CollectionTerms,
                               session=Depends(verify_session)):
    """Replace the market's collection terms.

    These are what actually gets searched. Changing them does not re-run
    collection; the next cycle picks them up once the group is rebuilt.
    """
    cleaned = list(dict.fromkeys(
        t.strip() for t in payload.terms if t and t.strip()))
    # Report what will really be searched. The normalizer truncates past 30
    # characters, and a term that quietly broadens is worse than one refused.
    truncated = [
        {"term": term, "searched_as": shortened}
        for term in cleaned
        for shortened in [mc.check_term(term)] if shortened
    ]

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            conn.execute(text("""
                UPDATE bw_markets
                SET config = COALESCE(config, '{}'::jsonb)
                             || jsonb_build_object('collection_terms',
                                                   CAST(:t AS JSONB)),
                    updated_at = NOW()
                WHERE id = :m
            """), {"m": market_id, "t": json.dumps(cleaned)})
            conn.commit()
            return {"terms": cleaned, "truncated": truncated}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/collection-plan")
async def collection_plan(market_id: int, qualifier: str = Query("security"),
                          vendor_names: str = Query("funded"),
                          session=Depends(verify_session)):
    """What the market's collection group would search for. Reads only."""
    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            plan = mc.plan_market_keywords(conn, market_id, qualifier,
                                           vendor_names)
            plan["group_name"] = f"{market['name']} - Market Watch"
            plan["topic_name"] = f"Market Monitoring {market['name']}"
            plan["existing"] = (market.get("config") or {}).get("collection")
            return plan
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.post("/markets/{market_id}/collection-setup")
async def collection_setup(market_id: int, payload: CollectionSetup,
                           session=Depends(verify_session)):
    """Create the market's collection topic and keyword group.

    One group for the whole market, not one per vendor. Brand Watcher's own
    setup-monitoring makes a group per brand, which is right for two brands and
    ruinous for 82 — each group polls the news providers on its own interval
    and spends the same finite quota.
    """
    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            result = mc.setup_market_collection(
                conn, get_database_instance(), market_id, market["name"],
                qualifier=payload.qualifier,
                vendor_names=payload.vendor_names,
                dry_run=payload.dry_run,
            )
            if not payload.dry_run:
                conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Source and schedule configuration
# ---------------------------------------------------------------------------


class SourceSetting(BaseModel):
    enabled: bool = True
    # Hours. Clamped at the floor by the loop — a market source polled faster
    # is spending money to learn nothing sooner.
    interval_hours: Optional[int] = Field(None, ge=1, le=8760)


@router.get("/markets/{market_id}/sources")
async def get_sources(market_id: int, session=Depends(verify_session)):
    """Every source, its schedule, and when it last ran."""
    from app.tasks import market_monitor as mm

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            overrides = mm.source_config(conn, market_id)
            last = {r[0]: r[1] for r in conn.execute(text("""
                SELECT source, MAX(started_at) FROM bw_collection_runs
                WHERE market_id = :m AND status = 'succeeded' GROUP BY 1
            """), {"m": market_id}).fetchall()}
            out = []
            for src in sorted(KNOWN_SOURCES | {mm.SOURCE_CANDIDATES,
                                              mm.SOURCE_CORPUS,
                                              mm.SOURCE_POST_REVIEW,
                                              mm.SOURCE_BRIEFING}):
                entry = overrides.get(src) if isinstance(overrides.get(src), dict) else {}
                out.append({
                    "source": src,
                    "paid": src in PAID_SOURCES,
                    "enabled": entry.get("enabled", True),
                    "interval_hours": entry.get("interval_hours"),
                    "default_interval_hours": round(
                        mm.cadence(src).total_seconds() / 3600),
                    "effective_interval_hours": round(
                        mm.cadence_for(conn, market_id, src).total_seconds() / 3600),
                    "last_success": last.get(src).isoformat() if last.get(src) else None,
                })
            return {"sources": out, "min_interval_hours": mm.MIN_INTERVAL_HOURS}
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.put("/markets/{market_id}/sources")
async def set_sources(market_id: int, payload: Dict[str, SourceSetting],
                      session=Depends(verify_session)):
    """Replace the per-source schedule and on/off settings."""
    cleaned = {
        src: {k: v for k, v in setting.model_dump().items() if v is not None}
        for src, setting in payload.items()
        if src in KNOWN_SOURCES
    }

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            conn.execute(text("""
                UPDATE bw_markets
                SET config = COALESCE(config, '{}'::jsonb)
                             || jsonb_build_object('sources', CAST(:s AS JSONB)),
                    updated_at = NOW()
                WHERE id = :m
            """), {"m": market_id, "s": json.dumps(cleaned)})
            conn.commit()
            return {"sources": cleaned}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Outputs: dataset, feed, brief
# ---------------------------------------------------------------------------


@router.get("/markets/{market_id}/dataset")
async def market_dataset(
    market_id: int,
    fmt: str = Query("json", pattern="^(json|csv)$"),
    session=Depends(verify_session),
):
    """The registry joined to its latest observations, one row per vendor."""
    from fastapi.responses import Response

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            return mp.build_dataset(conn, market_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_work)
    if fmt == "csv":
        return Response(
            content=mp.dataset_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="market-{market_id}-dataset.csv"'},
        )
    return {"rows": len(rows), "columns": mp.DATASET_COLUMNS, "data": rows}


@router.get("/markets/{market_id}/feed.xml")
async def market_feed(
    market_id: int,
    request: Request,
    kind: str = Query("all", pattern="^(all|articles|events)$"),
    classes: Optional[str] = Query(
        None, description="Comma-separated: news, vendor, social, research. "
                          "Defaults to news,vendor,research — vendor LinkedIn "
                          "posts are excluded unless asked for."),
    days: Optional[int] = Query(None, ge=1, le=3650),
    limit: int = Query(50, ge=1, le=200),
    session=Depends(verify_session_optional),
):
    """The market timeline as RSS, so the wire can be subscribed to.

    A feed reader carries no session. Behind ``verify_session`` this route
    answered every subscriber with a 307 to the login page, which is not a feed
    — so the session is optional here and a market marked ``is_public`` serves
    anonymously. A private market still needs a session, and answers 404 rather
    than redirecting, because a redirect is what broke it.
    """
    from fastapi.responses import Response

    base = (os.getenv("APP_URL") or "").rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")

    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            if not market.get("is_public") and not session:
                raise HTTPException(status_code=404, detail="Market not found")
            picked = [c.strip() for c in (classes or "").split(",") if c.strip()]
            return mp.build_feed(conn, market, base_url=base, kind=kind,
                                 classes=picked or None, days=days,
                                 limit=limit)
        finally:
            conn.close()

    xml = await asyncio.to_thread(_work)
    return Response(content=xml,
                    media_type="application/rss+xml; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=900"})


# Report sharing reuses the signal-report token scheme rather than inventing
# one: same secret, same HMAC, same expiry shape. A report link that expires is
# better than a public flag that does not, which is why this does not simply
# ride on ``bw_markets.is_public`` the way the feed does.
REPORT_LINK_TTL_SECONDS = 7 * 24 * 3600


def _market_report_token(market_id: int, exp: int) -> str:
    import hashlib
    import hmac

    from app.routes.vector_routes import _report_link_secret

    return hmac.new(_report_link_secret(),
                    f"market-report:{market_id}:{exp}".encode(),
                    hashlib.sha256).hexdigest()


@router.get("/markets/{market_id}/report-link")
async def market_report_link(
    market_id: int,
    days: int = Query(30, ge=1, le=365),
    session=Depends(verify_session),
):
    """A signed, expiring URL for the report that needs no login to open."""
    import time

    def _work():
        conn = _conn()
        try:
            return _load_market(conn, market_id)
        finally:
            conn.close()

    await asyncio.to_thread(_work)
    exp = int(time.time()) + REPORT_LINK_TTL_SECONDS
    token = _market_report_token(market_id, exp)
    base = (os.getenv("APP_URL") or "").rstrip("/")
    return {
        "url": (f"{base}/api/market-monitor/markets/{market_id}/report.html"
                f"?days={days}&exp={exp}&token={token}"),
        "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(),
        "ttl_days": REPORT_LINK_TTL_SECONDS // 86400,
    }


@router.get("/markets/{market_id}/report.html")
async def market_report(
    market_id: int,
    request: Request,
    days: int = Query(30, ge=1, le=365),
    exp: Optional[int] = Query(None),
    token: Optional[str] = Query(None),
    session=Depends(verify_session_optional),
):
    """The market as one self-contained HTML file.

    Three ways in, in order: a valid signed link, a session, or a public
    market. Anything else is a 404 rather than a redirect — a redirect is what
    made the feed unusable for machines.
    """
    import hmac
    import time

    from fastapi.responses import Response

    from app.services.market_report_html import build_market_report

    signed = bool(
        exp and token
        and exp > int(time.time())
        and hmac.compare_digest(token, _market_report_token(market_id, exp)))

    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            if not (signed or session or market.get("is_public")):
                raise HTTPException(status_code=404, detail="Market not found")
            return build_market_report(conn, market, days=days)
        finally:
            conn.close()

    html = await asyncio.to_thread(_work)
    return Response(content=html, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=300"})


@router.get("/markets/{market_id}/export.zip")
async def market_export_bundle(market_id: int,
                               session=Depends(verify_session)):
    """Every dataset this market holds, as one download.

    Nine CSVs, the registry and analyses as JSON, and a README saying what each
    file is and when it was collected. A folder of numbers with no note about
    where they came from is a folder somebody will misread in six months.
    """
    import io
    import zipfile

    from fastapi.responses import Response

    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            from app.services import market_analysis as man

            buf = io.BytesIO()
            stamp = datetime.now(timezone.utc)
            manifest = []
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in mp.DATASETS:
                    try:
                        rows = mp.build_table(conn, market_id, name)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("export %s failed: %s", name, exc)
                        continue
                    zf.writestr(f"{name}.csv", mp.table_csv(rows))
                    manifest.append((f"{name}.csv", len(rows),
                                     mp.DATASETS[name]))

                analyses = {}
                for name in man.ANALYSES:
                    try:
                        analyses[name] = man.run(conn, market_id, name)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("export analysis %s: %s", name, exc)
                payload = {
                    "market": {k: market[k] for k in
                               ("id", "name", "slug", "question",
                                "description")},
                    "generated_at": stamp.isoformat(),
                    "overview": mp.build_overview(conn, market, days=30),
                    "analyses": analyses,
                }
                zf.writestr("market.json",
                            json.dumps(payload, indent=1, default=str))

                readme = [
                    f'{market["name"]} — Market Monitor export',
                    f'Generated {stamp.strftime("%Y-%m-%d %H:%M UTC")}',
                    "",
                    (market.get("question") or "").strip(),
                    "",
                    "Files:",
                ]
                for filename, count, description in manifest:
                    readme.append(f"  {filename:16s} {count:>6} rows  {description}")
                readme += [
                    "  market.json           the registry, the standing "
                    "picture and the four analyses",
                    "",
                    "Notes:",
                    "  Every figure is a count of stored records. Nothing here "
                    "is estimated or modelled.",
                    "  Coverage varies by dataset: company measurements exist "
                    "only for vendors whose",
                    "  pages have been read, and each analysis in market.json "
                    "carries its own coverage.",
                    "  Vendor posts carry a review verdict saying whether the "
                    "post states a fact.",
                    "  Funding figures are floors — they cover disclosed "
                    "raises only.",
                ]
                zf.writestr("README.txt", "\n".join(readme))

            return market["slug"], buf.getvalue()
        finally:
            conn.close()

    slug, blob = await asyncio.to_thread(_work)
    name = f'{slug}-{datetime.now(timezone.utc).strftime("%Y-%m-%d")}.zip'
    return Response(content=blob, media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="{name}"'})


class BriefingRequest(BaseModel):
    year: Optional[int] = Field(None, ge=2000, le=2100)
    month: Optional[int] = Field(None, ge=1, le=12)
    model: Optional[str] = None
    store: bool = True


@router.post("/markets/{market_id}/briefings")
async def market_briefing_generate(market_id: int, body: BriefingRequest,
                                   session=Depends(verify_session)):
    """Write the monthly briefing: facts from stored rows, prose on top.

    Defaults to the last complete month. A briefing about the month in progress
    is one that will be wrong by the end of it.
    """
    from app.services import market_briefing as mbr

    year, month = body.year, body.month
    if not (year and month):
        year, month = mbr.previous_month()

    conn = _conn()
    try:
        market = await asyncio.to_thread(_load_market, conn, market_id)
        result = await mbr.generate(conn, market, year=year, month=month,
                                    model=body.model, store=body.store)
        # The facts block is large and the caller usually wants the prose. It
        # is stored either way and readable through the detail route.
        result.pop("facts", None)
        return result
    finally:
        conn.close()


@router.get("/markets/{market_id}/briefings")
async def market_briefings(market_id: int,
                           limit: int = Query(24, ge=1, le=120),
                           session=Depends(verify_session)):
    """Briefings for this market, newest period first."""
    from app.services import market_briefing as mbr

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            return {"briefings": mbr.listing(conn, market_id, limit)}
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/briefings/{briefing_id}")
async def market_briefing_detail(market_id: int, briefing_id: int,
                                 session=Depends(verify_session)):
    """One briefing, with the facts it was written from.

    The facts are returned deliberately: they are how a reader checks the
    prose. A figure in the briefing that is not in the facts is a fabrication,
    and without them that check cannot be made.
    """
    from app.services import market_briefing as mbr

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            row = mbr.get(conn, market_id, briefing_id)
            if not row:
                raise HTTPException(status_code=404, detail="Briefing not found")
            return row
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


class BriefingStatus(BaseModel):
    status: str = Field(..., pattern="^(draft|approved|rejected)$")


@router.put("/markets/{market_id}/briefings/{briefing_id}/status")
async def market_briefing_status(market_id: int, briefing_id: int,
                                 body: BriefingStatus,
                                 session=Depends(verify_session)):
    """Approve or reject a briefing. Regenerating one returns it to draft."""
    from app.services import market_briefing as mbr

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            if not mbr.set_status(conn, market_id, briefing_id, body.status):
                raise HTTPException(status_code=404, detail="Briefing not found")
            return {"ok": True, "id": briefing_id, "status": body.status}
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/drilldown/{name}")
async def market_drilldown(market_id: int, name: str,
                           session=Depends(verify_session)):
    """The vendors behind one figure on the overview.

    Every number on that page used to be a dead end. "62 vendors with no
    signal" is the most useful figure there and there was no way to see which
    62.
    """
    from app.services import market_analysis as man

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            try:
                return man.drilldown(conn, market_id, name)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/analysis/{name}")
async def market_analysis(market_id: int, name: str,
                          session=Depends(verify_session)):
    """One cross-sectional analysis of the market.

    ``formation`` — founding years against announcement volume.
    ``signal_noise`` — which vendors announce things and which just post.
    ``funding`` — stage mix, momentum, investors backing more than one vendor.
    ``hiring`` — what the market is recruiting for.

    Every one returns its own ``coverage``, because most of them rest on a
    subset of the registry and a figure without its denominator invites the
    wrong conclusion.
    """
    from app.services import market_analysis as man

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            try:
                return man.run(conn, market_id, name)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/analysis")
async def market_analysis_all(market_id: int,
                              session=Depends(verify_session)):
    """All four analyses in one call — what the Analysis view loads."""
    from app.services import market_analysis as man

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            out = {}
            for name in man.ANALYSES:
                try:
                    out[name] = man.run(conn, market_id, name)
                except Exception as exc:  # noqa: BLE001
                    # One failing analysis should not blank the whole view.
                    logger.warning("analysis %s failed: %s", name, exc)
                    out[name] = {"error": str(exc)[:300]}
            return out
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/data")
async def market_data_inventory(market_id: int,
                                session=Depends(verify_session)):
    """Everything this market has stored, with row counts and download links.

    The monitor writes to eight tables and the UI showed two of them, so the
    honest answer to "where can I see all of the data" was "you cannot". This
    is the index.
    """
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            return {"datasets": mp.data_inventory(conn, market_id)}
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/data/{dataset}")
async def market_dataset(
    market_id: int,
    dataset: str,
    fmt: str = Query("json", pattern="^(json|csv)$"),
    limit: int = Query(500, ge=1, le=5000),
    session=Depends(verify_session),
):
    """One dataset, as JSON for the table view or CSV for a spreadsheet."""
    from fastapi.responses import Response

    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            try:
                rows = mp.build_table(conn, market_id, dataset)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            return market, rows
        finally:
            conn.close()

    market, rows = await asyncio.to_thread(_work)

    if fmt == "csv":
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        name = f"{market['slug']}-{dataset}-{stamp}.csv"
        return Response(
            content=mp.table_csv(rows), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # The JSON form is for the on-screen table, so it is capped. The CSV is
    # not — a download that silently stopped at 500 rows would be worse than
    # no download.
    return {"dataset": dataset, "total": len(rows), "limit": limit,
            "rows": rows[:limit]}


class PostReviewRequest(BaseModel):
    limit: int = Field(200, ge=1, le=2000)
    batch: int = Field(20, ge=1, le=50)
    days: Optional[int] = Field(None, ge=1, le=3650)
    redo: bool = False
    dry_run: bool = False


@router.post("/markets/{market_id}/posts/review")
async def market_post_review(market_id: int, body: PostReviewRequest,
                             session=Depends(verify_session)):
    """Read unreviewed vendor posts and record what each one is.

    Vendor LinkedIn posts cannot be used wholesale — 562 against 122 news
    articles buries everything — and cannot be discarded either, because
    launches, raises and customer wins appear there first. No keyword rule
    separates the two, so each post is read once and judged, and only the ones
    judged to state a fact reach the feed, the timeline or an observer.

    Reviewed once, not per query: the judgement does not change, and asking
    again is paying twice for the same answer.
    """
    from app.services import market_post_review as mpr

    conn = _conn()
    try:
        market = await asyncio.to_thread(_load_market, conn, market_id)
        return await mpr.review(
            conn, market_id, market["name"],
            limit=body.limit, batch=body.batch, days=body.days,
            redo=body.redo, dry_run=body.dry_run)
    finally:
        conn.close()


@router.get("/markets/{market_id}/overview")
async def market_overview(
    market_id: int,
    days: int = Query(30, ge=1, le=365),
    session=Depends(verify_session),
):
    """The market's standing picture: coverage, money, activity, corpus.

    Separate from the brief, which is a change log for one week. A reader
    should not have to reconstruct the state of a market from a list of the
    week's events.
    """
    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            return mp.build_overview(conn, market, days=days)
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Corpus — the market's own language matched against articles we already have
# ---------------------------------------------------------------------------

class CorpusScanRequest(BaseModel):
    days: Optional[int] = Field(None, ge=1, le=3650)
    limit: int = Field(5000, ge=1, le=100000)
    min_score: float = Field(12.0, ge=0, le=100)
    require_analyzed: bool = False
    dry_run: bool = False
    terms: Optional[List[str]] = None


@router.post("/markets/{market_id}/corpus/scan")
async def market_corpus_scan(market_id: int, body: CorpusScanRequest,
                             session=Depends(verify_session)):
    """Match the existing article corpus against the market's phrases.

    Brand Watcher's classifier answers "which articles named this vendor". This
    answers "which articles are about this category", which is a different
    question and the one a market brief is written from. It reads articles that
    were already collected and analysed, so it calls no provider and costs
    nothing beyond the query.

    ``dry_run`` writes nothing, so a proposed term list can be measured before
    it is adopted.
    """
    from app.services import market_corpus as mcorp

    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            result = mcorp.scan(
                conn, market_id,
                terms=body.terms,
                topic_name=mcorp.market_topic_name(market),
                days=body.days, limit=body.limit,
                min_score=body.min_score,
                require_analyzed=body.require_analyzed,
                dry_run=body.dry_run,
            )
            if not body.dry_run:
                conn.commit()
            return result
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/corpus")
async def market_corpus_articles(
    market_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    days: Optional[int] = Query(None, ge=1, le=3650),
    origin: Optional[str] = Query(None),
    classes: Optional[str] = Query(
        None, description="Comma-separated: news, vendor, social, research."),
    min_score: float = Query(0.0, ge=0, le=100),
    all_posts: bool = Query(
        False, description="Include vendor posts the review judged noise. Off "
                           "by default — a post is shown once it is known to "
                           "say something."),
    session=Depends(verify_session),
):
    """The matched corpus, newest first."""
    from app.services import market_corpus as mcorp

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            return {
                "articles": mcorp.articles(
                    conn, market_id, limit=limit, offset=offset, days=days,
                    origin=origin, min_score=min_score,
                    classes=[c.strip() for c in (classes or "").split(",")
                             if c.strip()] or None,
                    require_signal_for_social=not all_posts),
                "limit": limit, "offset": offset,
            }
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/corpus/summary")
async def market_corpus_summary(
    market_id: int,
    days: int = Query(30, ge=1, le=365),
    session=Depends(verify_session),
):
    """Counts, top phrases and top sources for the matched corpus."""
    from app.services import market_corpus as mcorp

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            out = mcorp.summary(conn, market_id, days=days)
            out["collection_terms"] = mc.market_terms(conn, market_id)
            out["context_terms"] = mcorp.context_terms(conn, market_id)
            return out
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/brief")
async def market_brief(
    market_id: int,
    days: int = Query(7, ge=1, le=90),
    session=Depends(verify_session),
):
    """What changed, who moved, and what is still unknown.

    Assembled from stored rows. The timeline already did the extraction; asking
    a model to re-summarise its own summary costs money for a different answer
    to the same question.
    """
    def _work():
        conn = _conn()
        try:
            market = _load_market(conn, market_id)
            return mp.build_brief(conn, market, days=days)
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Discovery — vendors the registry does not have yet
# ---------------------------------------------------------------------------


@router.post("/markets/{market_id}/discover")
async def discover_candidates(
    market_id: int,
    days: int = Query(14, ge=1, le=180),
    min_alignment: float = Query(0.4, ge=0.0, le=1.0),
    dry_run: bool = Query(False),
    session=Depends(verify_session),
):
    """Read the market's recent funding coverage and propose new vendors.

    A registry goes stale the moment it is imported, and in this category new
    entrants announce themselves by raising money. Each unknown company becomes
    a review task with the article behind it — never a vendor added on a
    headline's say-so.
    """
    from app.services import market_discovery as md

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            result = md.discover_funding_candidates(
                conn, market_id, days=days, min_alignment=min_alignment,
                dry_run=dry_run)
            if not dry_run:
                conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Collection health and manual runs
# ---------------------------------------------------------------------------

@router.get("/markets/{market_id}/source-health")
async def source_health(market_id: int, session=Depends(verify_session)):
    """Per-source freshness and outcome.

    "Failed" and "ran but found nothing" are reported as different things.
    Collapsing them is how a broken source hides for a month behind a quiet
    dashboard.

    Spend is deliberately absent. ``bw_collection_runs.cost_amount`` exists and
    is always NULL — the provider does not return a price with a job and no
    caller computes one — so reporting it as a number implied we track spend
    when we do not. The column stays for the day there is a price list.
    """
    from app.services.brightdata_linkedin import linkedin_enabled, webhook_secret

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            # Health is the state of the most recent run, not a tally over 30
            # days. A source that failed once and has succeeded twice since is
            # working; reporting the old error as current sends someone to
            # debug a bug that was fixed.
            rows = conn.execute(text("""
                SELECT source, provider,
                       COUNT(*) AS runs,
                       COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                       COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
                       COUNT(*) FILTER (WHERE status IN ('queued','running'))
                           AS in_flight,
                       MAX(started_at) FILTER (WHERE status = 'succeeded')
                           AS last_success,
                       MAX(started_at) AS last_attempt,
                       SUM(records_new) AS records_new,
                       SUM(records_received) AS records_received,
                       (ARRAY_AGG(status ORDER BY started_at DESC))[1]
                           AS latest_status,
                       (ARRAY_AGG(error ORDER BY started_at DESC))[1]
                           AS latest_error
                FROM bw_collection_runs
                WHERE market_id = :m AND started_at >= NOW() - INTERVAL '30 days'
                GROUP BY source, provider ORDER BY source
            """), {"m": market_id}).mappings().all()
            sources = []
            for r in rows:
                row = dict(r)
                last = row.get("last_success")
                row["stale_hours"] = (
                    round((datetime.now(timezone.utc) - last).total_seconds() / 3600, 1)
                    if last else None
                )
                latest = row.pop("latest_status", None)
                latest_error = row.pop("latest_error", None)
                # In flight is neither healthy nor failing — it is pending.
                row["state"] = (
                    "in_flight" if latest in ("queued", "running")
                    else "failing" if latest == "failed"
                    else "healthy" if latest == "succeeded"
                    else "unknown"
                )
                row["healthy"] = row["state"] == "healthy"
                # Only surface the error when the most recent run is the one
                # that failed. Historical errors stay in the run log.
                row["last_error"] = latest_error if latest == "failed" else None
                row["found_nothing"] = bool(last) and (row.get("records_new") or 0) == 0
                sources.append(row)
            coverage = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE mb.collection_enabled
                                        AND mb.role <> 'excluded') AS collecting,
                       COUNT(*) FILTER (WHERE NOT EXISTS (
                           SELECT 1 FROM bw_vendor_identifiers i
                           WHERE i.brand_id = mb.brand_id AND i.valid_to IS NULL
                             AND i.kind = 'linkedin_company_url')
                           AND mb.role <> 'excluded') AS without_linkedin
                FROM bw_market_brands mb WHERE mb.market_id = :m
            """), {"m": market_id}).mappings().first()
            return {
                "market_id": market_id,
                "sources": sources,
                "coverage": dict(coverage or {}),
                "providers": {
                    "brightdata_linkedin_enabled": linkedin_enabled(),
                    "webhook_secret_set": bool(webhook_secret()),
                },
            }
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.get("/markets/{market_id}/runs")
async def list_runs(market_id: int, source: Optional[str] = Query(None),
                    limit: int = Query(50, ge=1, le=500),
                    session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            sql = """SELECT r.id, r.brand_id, r.source, r.provider, r.job_id,
                            r.status, r.records_received, r.records_new,
                            r.records_skipped, r.started_at, r.completed_at,
                            r.latency_ms, r.error,
                            b.display_name AS vendor
                     FROM bw_collection_runs r
                     LEFT JOIN bw_brands b ON b.id = r.brand_id
                     WHERE r.market_id = :m"""
            params: Dict[str, Any] = {"m": market_id, "lim": limit}
            if source:
                sql += " AND r.source = :s"
                params["s"] = source
            sql += " ORDER BY r.started_at DESC LIMIT :lim"
            return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


@router.post("/markets/{market_id}/runs", status_code=202)
async def start_run(market_id: int, payload: ManualRun,
                    session=Depends(verify_session)):
    """Queue a manual collection run and return its id immediately.

    202 with a durable row rather than 200 with a background closure: a Bright
    Data batch outlives the request that started it, and a restart mid-flight
    must leave something behind that a callback can still find.
    """
    from app.services.brightdata_linkedin import linkedin_enabled

    if payload.source not in KNOWN_SOURCES:
        raise HTTPException(
            400, f"Unknown source. Expected one of: {', '.join(sorted(KNOWN_SOURCES))}")
    if payload.source in PAID_SOURCES and not linkedin_enabled():
        raise HTTPException(
            409, "Bright Data LinkedIn collection is disabled "
                 "(BRIGHTDATA_LINKEDIN_ENABLED).")

    provider = "brightdata" if payload.source in PAID_SOURCES else "internal"

    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            run_id = conn.execute(text("""
                INSERT INTO bw_collection_runs (market_id, source, provider, status)
                VALUES (:m, :s, :p, 'queued') RETURNING id
            """), {"m": market_id, "s": payload.source, "p": provider}).scalar()
            conn.commit()
            return {"run_id": run_id, "status": "queued", "source": payload.source}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Provider callback — no session, by necessity
# ---------------------------------------------------------------------------

_TERMINAL = {"succeeded", "failed", "cancelled", "partial"}


def callback_url(run_id: int) -> str:
    """Where Bright Data should post this run's results.

    The run id travels in the URL because the payload does not reliably carry
    anything identifying the batch — and a value from a request body is not
    something we would use to choose a market.
    """
    import os

    base = (os.getenv("APP_URL") or os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}/api/market-monitor/webhooks/brightdata/linkedin?run_id={run_id}"


def _records_from(body: Any):
    """Bright Data posts either the records themselves or a status envelope."""
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if isinstance(body, dict):
        for key in ("data", "records", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return None


@router.post("/webhooks/brightdata/linkedin", include_in_schema=False)
async def brightdata_linkedin_callback(
    request: Request,
    run_id: int = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Accept an async Bright Data delivery.

    Declares no ``verify_session`` on purpose — a provider has no session. It
    authenticates on the shared secret the provider echoes back, which is
    fail-closed on an unset secret, and takes its market from the run row
    rather than from anything in the body.
    """
    from app.services.brightdata_linkedin import verify_webhook_auth

    if not verify_webhook_auth(authorization):
        # Same 401 whether the secret is unset, absent or wrong: a caller
        # probing this endpoint learns nothing about which.
        logger.warning("brightdata webhook: rejected delivery for run %s", run_id)
        raise HTTPException(401, "Unauthorized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body is not JSON")

    def _work():
        conn = _conn()
        try:
            run = mc.load_run(conn, run_id)
            if run is None:
                raise HTTPException(404, "Unknown run")
            if run["status"] in _TERMINAL:
                # Bright Data retries; a retry must not double-count records.
                return {"status": "already_processed", "run_id": run_id,
                        "run_status": run["status"]}

            records = _records_from(body)
            if records is None:
                state = (body or {}).get("status") if isinstance(body, dict) else None
                if str(state).lower() in ("failed", "error"):
                    mc.close_run(conn, run_id, status="failed",
                                 error=f"provider reported {state}")
                    conn.commit()
                    return {"status": "failed", "run_id": run_id}
                conn.commit()
                return {"status": "acknowledged", "run_id": run_id}

            result = mc.ingest_for_source(conn, run=run, records=records)
            mc.close_run(
                conn, run_id,
                status=mc.outcome_status(len(records), result.get("stored", 0),
                                         result.get("provider_errors", 0)),
                received=len(records),
                new=result.get("stored", 0),
                skipped=(result.get("unchanged", 0) + result.get("unmatched", 0)
                         + result.get("dropped", 0)),
            )
            conn.commit()
            return {"status": "ok", "run_id": run_id, **result}
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            logger.exception("brightdata webhook: ingest failed for run %s", run_id)
            # Record the failure, or the run sits in "running" forever with
            # nobody looking for it.
            try:
                mc.close_run(conn, run_id, status="failed", error=str(e))
                conn.commit()
            except Exception:
                conn.rollback()
            raise HTTPException(500, "Ingest failed")
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# One vendor, everything we hold
# ---------------------------------------------------------------------------
#
# Declared after /vendors/facets so the static path wins the match. One call
# rather than six: the page needs all of this at once, and six round trips
# would render six times.


@router.get("/markets/{market_id}/vendors/{brand_id}")
async def vendor_detail(market_id: int, brand_id: int,
                        session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _load_market(conn, market_id)
            row = conn.execute(text("""
                SELECT mb.brand_id, mb.role, mb.collection_enabled, mb.is_public,
                       mb.review_status, mb.baseline, mb.sort_order,
                       b.name AS slug, b.display_name, b.enabled, b.brand_keywords
                FROM bw_market_brands mb
                JOIN bw_brands b ON b.id = mb.brand_id
                WHERE mb.market_id = :m AND mb.brand_id = :b
            """), {"m": market_id, "b": brand_id}).mappings().first()
            if not row:
                raise HTTPException(404, "Vendor not in this market")
            vendor = dict(row)

            # Live and superseded together. A corrected identifier is part of
            # how the registry got here — Crogl's crossed LinkedIn URL is the
            # reason one of its numbers was wrong for a day.
            vendor["identifiers"] = [dict(r) for r in conn.execute(text("""
                SELECT kind, display_value, normalized_value, provenance,
                       verified_at IS NOT NULL AS verified,
                       valid_to IS NULL AS live, valid_to
                FROM bw_vendor_identifiers WHERE brand_id = :b
                ORDER BY valid_to IS NOT NULL, kind
            """), {"b": brand_id}).mappings().all()]

            # Ascending: this is the series the headcount chart plots. The
            # workbook value is a reference line, not its first point.
            vendor["profile_series"] = [dict(r) for r in conn.execute(text("""
                SELECT observed_at,
                       (data->>'employee_count')::numeric AS employee_count,
                       (data->>'followers')::numeric AS followers
                FROM bw_vendor_snapshots
                WHERE brand_id = :b AND snapshot_type = 'profile'
                ORDER BY observed_at
            """), {"b": brand_id}).mappings().all()]

            vendor["funding"] = conn.execute(text("""
                SELECT data FROM bw_vendor_snapshots
                WHERE brand_id = :b AND snapshot_type = 'funding'
                ORDER BY observed_at DESC LIMIT 1
            """), {"b": brand_id}).scalar()

            # Latest state per watched page, with whatever changed last time.
            vendor["pages"] = [dict(r) for r in conn.execute(text("""
                SELECT DISTINCT ON (provider_item_id)
                       provider_item_id AS url, observed_at,
                       data->>'kind' AS kind, data->>'title' AS title,
                       data->'diff' AS diff, data->>'http_status' AS http_status
                FROM bw_vendor_snapshots
                WHERE brand_id = :b AND snapshot_type = 'page_state'
                ORDER BY provider_item_id, observed_at DESC
            """), {"b": brand_id}).mappings().all()]

            vendor["jobs"] = [dict(r) for r in conn.execute(text("""
                SELECT DISTINCT ON (provider_item_id)
                       data->>'title' AS title, data->>'location' AS location,
                       data->>'seniority' AS seniority, data->>'function' AS function,
                       data->>'posted_date' AS posted_date, data->>'url' AS url
                FROM bw_vendor_snapshots
                WHERE brand_id = :b AND snapshot_type = 'job_posting'
                ORDER BY provider_item_id, observed_at DESC
            """), {"b": brand_id}).mappings().all()]

            # DISTINCT ON the uri, not just an ORDER BY: bw_article_categories
            # is keyed on (article, brand, category), so a post filed under
            # three categories was taking three of these ten slots.
            vendor["posts"] = [dict(r) for r in conn.execute(text("""
                SELECT * FROM (
                    SELECT DISTINCT ON (a.uri)
                           a.uri, a.title, a.summary, a.publication_date,
                           a.url, a.social_meta
                    FROM bw_article_categories bac
                    JOIN articles a ON a.uri = bac.article_uri
                    WHERE bac.brand_id = :b
                      AND a.bias_source = 'vendor:linkedin'
                    ORDER BY a.uri, a.publication_date DESC
                ) p
                ORDER BY p.publication_date DESC NULLS LAST LIMIT 10
            """), {"b": brand_id}).mappings().all()]

            # What this vendor actually announced, as opposed to what it
            # posted. Without the split a product launch sits in the same list
            # as a conference booth notice.
            vendor["announcements"] = [dict(r) for r in conn.execute(text("""
                SELECT * FROM (
                    SELECT DISTINCT ON (a.uri)
                           a.uri, a.title, a.publication_date, a.url,
                           ma.review_kind, ma.review_reason
                    FROM bw_article_categories bac
                    JOIN articles a ON a.uri = bac.article_uri
                    JOIN bw_market_articles ma ON ma.article_uri = a.uri
                    WHERE bac.brand_id = :b
                      AND ma.review_verdict = 'signal'
                    ORDER BY a.uri, a.publication_date DESC
                ) p
                ORDER BY p.publication_date DESC NULLS LAST LIMIT 25
            """), {"b": brand_id}).mappings().all()]

            vendor["post_verdicts"] = dict(conn.execute(text("""
                SELECT ma.review_verdict, COUNT(DISTINCT ma.article_uri)
                FROM bw_market_articles ma
                JOIN bw_article_categories bac
                     ON bac.article_uri = ma.article_uri
                WHERE bac.brand_id = :b AND ma.review_verdict IS NOT NULL
                GROUP BY 1
            """), {"b": brand_id}).fetchall())

            vendor["coverage_by_category"] = [dict(r) for r in conn.execute(text("""
                SELECT category, COUNT(*) AS n FROM bw_article_categories
                WHERE brand_id = :b GROUP BY 1 ORDER BY 2 DESC
            """), {"b": brand_id}).mappings().all()]

            vendor["recent_coverage"] = [dict(r) for r in conn.execute(text("""
                SELECT DISTINCT ON (a.uri) a.uri, a.title, a.news_source,
                       a.publication_date, a.sentiment, a.url
                FROM bw_article_categories bac
                JOIN articles a ON a.uri = bac.article_uri
                WHERE bac.brand_id = :b
                  AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
                ORDER BY a.uri, a.publication_date DESC LIMIT 10
            """), {"b": brand_id}).mappings().all()]

            vendor["review_tasks"] = [dict(r) for r in conn.execute(text("""
                SELECT id, kind, severity, status, field, message
                FROM bw_review_tasks WHERE brand_id = :b AND status = 'open'
                ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1
                                       ELSE 2 END
            """), {"b": brand_id}).mappings().all()]

            vendor["feeds"] = [dict(r) for r in conn.execute(text("""
                SELECT name, url, is_active, last_checked_at, articles_fetched
                FROM rss_feeds WHERE name LIKE :n
            """), {"n": f"{vendor['display_name']}%"}).mappings().all()]

            return vendor
        finally:
            conn.close()

    return await asyncio.to_thread(_work)
