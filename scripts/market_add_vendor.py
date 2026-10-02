"""Add one vendor to a market's registry with everything the pages need, or
audit what existing vendors are missing.

The POST /markets/{id}/vendors route creates only the brand, the registry row
and a domain. Vendors added that way, by hand, ended up without a logo, a
colour, a category, a funding record or LinkedIn and Crunchbase links, and
nothing said so. This script does every step from one spec file and then runs
the audit on the result. The checklist it follows is
docs/MARKET_ADD_VENDOR_CHECKLIST.md.

Dry by default; ``--apply`` writes.

    .venv/bin/python scripts/market_add_vendor.py add spec.json [--apply]
    .venv/bin/python scripts/market_add_vendor.py colour --brand 90 --hex '#ef3340' --source logo [--apply]
    .venv/bin/python scripts/market_add_vendor.py audit --market 2 [--brand 90]

Spec file (JSON):

    {"market_id": 2,
     "display_name": "Tracecat",
     "website": "https://www.tracecat.com",
     "linkedin_url": "https://www.linkedin.com/company/tracecathq",
     "crunchbase_slug": "tracecat",
     "social": ["https://x.com/tracecathq"],
     "brand_keywords": ["Tracecat"],
     "search_name": null,
     "category": "AI Security", "sub_category": "SOC Automation",
     "hq_country": "United States", "founded_year": 2024,
     "funding": {"status": "Disclosed", "total_musd": 1.5,
                 "notes": "...", "sources": ["..."]},
     "colour": {"hex": "#181818", "source": "logo (black)"},
     "control_note": null,
     "provenance": {"source": "top_voices", "request_id": 33}}
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

# Per-vendor reads that need a paid Bright Data call. The scheduler would get
# to them on its own (a never-tried policy sorts first), but queuing them now
# gives the vendor a headcount and posts within the hour instead of the day.
FIRST_READS = ("linkedin_company_profile", "linkedin_company_post", "crunchbase_company")

REQUIRED_IDENTIFIERS = ("domain", "website_url", "linkedin_company_url", "crunchbase_url")


def _load_env() -> None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- colour
# A brand colour is fitted into a middle lightness band so the same dot reads
# on the light page and the dark chart surface. Same method as the colours set
# on 1 Oct 2026 (commit ecd85a13): OKLCH lightness clamped to 0.48-0.70,
# chroma reduced until the colour is inside sRGB.
_LO, _HI = 0.48, 0.70


def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _hex_to_oklch(h):
    r, g, b = (_s2l(int(h[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (x ** (1 / 3) for x in (l, m, s))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.atan2(bb, a)


def _oklch_to_rgb(L, C, H):
    a, b = C * math.cos(H), C * math.sin(H)
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def fit_colour(hex_colour: str):
    """(chart colour, adjusted?) for a brand colour as found."""
    h = hex_colour.lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", h):
        raise ValueError(f"not a #rrggbb colour: {hex_colour}")
    L, C, H = _hex_to_oklch(h)
    L2 = min(max(L, _LO), _HI)
    while True:
        rgb = _oklch_to_rgb(L2, C, H)
        if all(-1e-4 <= v <= 1 + 1e-4 for v in rgb) or C <= 0:
            break
        C -= 0.002
    out = "#" + "".join("%02x" % round(max(0, min(1, _l2s(max(0, v)))) * 255) for v in rgb)
    return out, abs(L - L2) > 0.005


def _set_colour(conn, brand_id: int, hex_colour: str, source: str) -> str:
    chart, adjusted = fit_colour(hex_colour)
    conn.execute(text("""
        UPDATE bw_brands
           SET color = :c,
               config = COALESCE(config, '{}'::jsonb)
                        || jsonb_build_object('brand_colour', CAST(:bc AS JSONB)),
               updated_at = NOW()
         WHERE id = :b
    """), {"c": chart, "b": brand_id, "bc": json.dumps({
        "brand": hex_colour.lower(), "chart": chart, "source": source,
        "adjusted_for_legibility": adjusted,
        "set": datetime.now(timezone.utc).date().isoformat()})})
    return chart


# ---------------------------------------------------------------- add
def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip()).split("/")[0].lower()


def _social_key(url: str):
    """('twitter:handle', url) for an X / Bluesky / Reddit profile link."""
    u = url.strip().rstrip("/")
    m = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)$", u)
    if m:
        return f"twitter:{m.group(1).lower()}"
    m = re.match(r"https?://bsky\.app/profile/([^/]+)$", u)
    if m:
        return f"bluesky:{m.group(1).lower()}"
    m = re.match(r"https?://(?:www\.)?reddit\.com/user/([^/]+)$", u)
    if m:
        return f"reddit:{m.group(1).lower()}"
    raise ValueError(f"unrecognised social profile URL: {url}")


def _identifier(conn, brand_id, kind, normalized, display, provenance):
    """Insert one active identifier unless this brand already has it."""
    owner = conn.execute(text("""
        SELECT brand_id FROM bw_vendor_identifiers
         WHERE kind = :k AND normalized_value = :n AND valid_to IS NULL
    """), {"k": kind, "n": normalized}).scalar()
    if owner is not None and owner != brand_id:
        raise RuntimeError(f"{kind} {normalized} already belongs to brand {owner}")
    if owner == brand_id:
        return False
    conn.execute(text("""
        INSERT INTO bw_vendor_identifiers
            (brand_id, kind, normalized_value, display_value, provenance)
        VALUES (:b, :k, :n, :d, CAST(:p AS JSONB))
    """), {"b": brand_id, "k": kind, "n": normalized, "d": display,
           "p": json.dumps(provenance)})
    return True


def add(spec: dict, apply: bool) -> int:
    from app.database import get_database_instance
    from app.services.market_collect import resync_market_keywords
    from app.services.entity_scheduler import seed_policies
    from fetch_vendor_logos import find_mark, _google_default_fingerprint

    market_id = int(spec["market_id"])
    name = spec["display_name"].strip()
    website = spec["website"].strip()
    domain = _domain(website)
    prov = {"source": "manual", **(spec.get("provenance") or {}),
            "added": datetime.now(timezone.utc).date().isoformat()}
    funding = spec.get("funding") or {}
    if funding.get("status") not in ("Disclosed", "Undisclosed", "Bootstrapped"):
        raise SystemExit("funding.status must be Disclosed, Undisclosed or Bootstrapped")
    if funding["status"] == "Disclosed" and not isinstance(funding.get("total_musd"), (int, float)):
        raise SystemExit("a Disclosed funding record needs total_musd")
    if not spec.get("brand_keywords"):
        raise SystemExit("brand_keywords is required (compound terms if the name is generic)")
    if not spec.get("linkedin_url"):
        raise SystemExit("linkedin_url is required: headcount, posts and jobs all read it")

    print(f"logo: looking on {website}")
    logo_uri, logo_src = find_mark(website, _google_default_fingerprint())
    print(f"logo: {'found ' + str(logo_src)[:90] if logo_uri else 'NONE (' + str(logo_src) + ')'}")

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        market = conn.execute(text("SELECT id, name FROM bw_markets WHERE id = :m"),
                              {"m": market_id}).mappings().first()
        if not market:
            raise SystemExit(f"no market {market_id}")

        # 1. Brand and registry row (same rules as POST /markets/{id}/vendors).
        brand_id = conn.execute(text("SELECT id FROM bw_brands WHERE display_name = :n"),
                                {"n": name}).scalar()
        if brand_id is None:
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100]
            brand_id = conn.execute(text("""
                INSERT INTO bw_brands (name, display_name, brand_keywords)
                VALUES (:s, :n, '[]'::jsonb) RETURNING id
            """), {"s": slug, "n": name}).scalar()
            print(f"brand: created {brand_id}")
        else:
            print(f"brand: reusing {brand_id}")
        if conn.execute(text("""SELECT 1 FROM bw_market_brands
                                 WHERE market_id = :m AND brand_id = :b"""),
                        {"m": market_id, "b": brand_id}).first():
            raise SystemExit(f"{name} is already in market {market_id}; use audit")
        conn.execute(text("""
            INSERT INTO bw_market_brands
                (market_id, brand_id, role, sort_order, collection_enabled,
                 social_collection_enabled, social_collection_config,
                 category, sub_category, baseline)
            VALUES (:m, :b, 'vendor',
                    (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM bw_market_brands WHERE market_id = :m),
                    TRUE, TRUE, '{}'::jsonb, :cat, :sub, CAST(:base AS JSONB))
        """), {"m": market_id, "b": brand_id, "cat": spec["category"],
               "sub": spec["sub_category"], "base": json.dumps({
                   "taxonomy": {"category": spec["category"],
                                "sub_category": spec["sub_category"]},
                   "hq_country": spec.get("hq_country"),
                   "founded_year": spec.get("founded_year"),
                   "funding_baseline": {k: funding.get(k) for k in
                                        ("status", "total_musd", "notes", "sources")},
                   "provenance": [prov]})})

        # 2. Keywords: what the classifier and the corpus scan match on.
        conn.execute(text("""
            UPDATE bw_brands SET brand_keywords = CAST(:kw AS JSONB), updated_at = NOW()
             WHERE id = :b
        """), {"kw": json.dumps(spec["brand_keywords"]), "b": brand_id})

        # 3. Identifiers. LinkedIn feeds headcount, posts and jobs; Crunchbase
        # feeds funding rounds; search_name replaces a generic name in searches.
        added = []
        for kind, norm, disp in (
            ("domain", domain, domain),
            ("website_url", website.rstrip("/").lower(), website),
            ("linkedin_company_url", spec["linkedin_url"].rstrip("/").lower(),
             spec["linkedin_url"]),
        ):
            if _identifier(conn, brand_id, kind, norm, disp, prov):
                added.append(kind)
        if spec.get("crunchbase_slug"):
            url = f"https://www.crunchbase.com/organization/{spec['crunchbase_slug']}"
            if _identifier(conn, brand_id, "crunchbase_url", url, url, prov):
                added.append("crunchbase_url")
        if spec.get("search_name"):
            if _identifier(conn, brand_id, "search_name", spec["search_name"].lower(),
                           spec["search_name"], prov):
                added.append("search_name")
        for url in spec.get("social") or []:
            if _identifier(conn, brand_id, "social_account", _social_key(url), url, prov):
                added.append("social_account")
        print(f"identifiers: {', '.join(added) or 'none new'}")

        # 4. Logo and colour.
        if logo_uri:
            conn.execute(text("""
                UPDATE bw_brands SET logo_data = :d, logo_source = :s, logo_fetched_at = NOW()
                 WHERE id = :b
            """), {"d": logo_uri, "s": logo_src, "b": brand_id})
        if spec.get("colour"):
            chart = _set_colour(conn, brand_id, spec["colour"]["hex"], spec["colour"]["source"])
            print(f"colour: {spec['colour']['hex']} -> chart {chart}")

        # 5. Analyst note on the maturity map, when the vendor needs explaining.
        if spec.get("control_note"):
            conn.execute(text("""
                INSERT INTO bw_market_vendor_controls
                    (market_id, brand_id, multipliers, note, status, updated_by, updated_at)
                VALUES (:m, :b, '{}'::jsonb, :n, 'active', 'market_add_vendor.py', NOW())
            """), {"m": market_id, "b": brand_id, "n": spec["control_note"]})

        if not apply:
            conn.rollback()
            print("dry run: rolled back; add --apply to write")
            return 0
        conn.commit()

        # 6. Search for the vendor from the next cycle, and create its
        # collection schedule. Both are idempotent.
        synced = resync_market_keywords(conn, db, market_id, market["name"])
        conn.commit()
        print(f"keywords added to the market group: {(synced or {}).get('keywords_added')}")
        summary = seed_policies(conn)
        conn.commit()
        print(f"policies: created {summary.get('created')}, updated {summary.get('updated')}")

        # 7. First paid reads, so the vendor has a headcount and posts today.
        for source in FIRST_READS:
            run_id = conn.execute(text("""
                INSERT INTO bw_collection_runs (market_id, brand_id, source, provider, status)
                VALUES (:m, :b, :s, 'brightdata', 'queued') RETURNING id
            """), {"m": market_id, "b": brand_id, "s": source}).scalar()
            print(f"queued {source}: run {run_id}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return audit(market_id, brand_id)


# ---------------------------------------------------------------- audit
def _gaps(conn, market_id: int, brand_id=None):
    rows = conn.execute(text("""
        SELECT b.id, b.display_name, b.brand_keywords, b.color, b.logo_data IS NOT NULL AS logo,
               mb.category, mb.sub_category, mb.social_collection_enabled, mb.baseline,
               (SELECT array_agg(DISTINCT i.kind) FROM bw_vendor_identifiers i
                 WHERE i.brand_id = b.id AND i.valid_to IS NULL) AS kinds,
               (SELECT count(*) FROM bw_entity_source_policies p WHERE p.brand_id = b.id) AS policies,
               (SELECT count(*) FROM bw_entity_source_policies p
                 WHERE p.brand_id = b.id AND p.eligible) AS eligible,
               (SELECT employee_count FROM bw_entity_profiles p WHERE p.brand_id = b.id) AS headcount,
               (SELECT count(*) FROM bw_collection_runs r
                 WHERE r.brand_id = b.id AND r.source = 'linkedin_company_profile'
                   AND r.status IN ('queued', 'running')) AS profile_pending
          FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role = 'vendor' AND mb.collection_enabled
           AND (CAST(:b AS INTEGER) IS NULL OR b.id = :b)
         ORDER BY b.display_name
    """), {"m": market_id, "b": brand_id}).mappings().all()
    out = []
    for r in rows:
        base = r["baseline"] or {}
        kinds = set(r["kinds"] or [])
        gaps = [f"identifier {k}" for k in REQUIRED_IDENTIFIERS if k not in kinds]
        if not r["brand_keywords"]:
            gaps.append("brand_keywords")
        if not r["category"] or not r["sub_category"]:
            gaps.append("category")
        if not (base.get("funding_baseline") or {}).get("status"):
            gaps.append("funding_baseline")
        if not base.get("hq_country"):
            gaps.append("hq_country")
        if not r["logo"]:
            gaps.append("logo")
        if not r["color"]:
            gaps.append("colour")
        if not r["social_collection_enabled"]:
            gaps.append("social collection off")
        if r["policies"] < 8:
            gaps.append(f"policies {r['policies']}/8 (run seed_policies)")
        if r["headcount"] is None:
            gaps.append("headcount (LinkedIn read queued)" if r["profile_pending"]
                        else "headcount (no LinkedIn profile read yet)")
        out.append((r["id"], r["display_name"], gaps, r["eligible"]))
    return out


def audit(market_id: int, brand_id=None) -> int:
    from app.database import get_database_instance

    conn = get_database_instance()._temp_get_connection()
    try:
        rows = _gaps(conn, market_id, brand_id)
    finally:
        conn.close()
    missing = [r for r in rows if r[2]]
    for bid, name, gaps, eligible in missing:
        print(f"{bid:>6}  {name:28} {'; '.join(gaps)}")
    print(f"{len(rows)} collecting vendors checked; {len(missing)} with gaps")
    if brand_id and rows:
        print(f"eligible collection policies: {rows[0][3]} of 8 "
              "(ats_jobs waits for ats_discovery, so 7 is normal for a new vendor)")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("spec")
    a.add_argument("--apply", action="store_true")
    c = sub.add_parser("colour")
    c.add_argument("--brand", type=int, required=True)
    c.add_argument("--hex", required=True)
    c.add_argument("--source", required=True, help='where the colour came from, e.g. "logo"')
    c.add_argument("--apply", action="store_true")
    u = sub.add_parser("audit")
    u.add_argument("--market", type=int, required=True)
    u.add_argument("--brand", type=int)
    args = ap.parse_args()
    _load_env()

    if args.cmd == "add":
        return add(json.load(open(args.spec)), args.apply)
    if args.cmd == "audit":
        return audit(args.market, args.brand)

    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        chart = _set_colour(conn, args.brand, args.hex, args.source)
        print(f"brand {args.brand}: {args.hex} -> chart {chart}")
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
            print("dry run; add --apply to write")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
