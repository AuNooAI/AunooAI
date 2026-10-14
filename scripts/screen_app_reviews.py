#!/usr/bin/env python3
"""Run the risk check over app reviews already stored.

New app reviews are screened as they land (bw_official_sources._risk_pass,
with the health vocabulary on). This applies the same gate and model to
reviews stored before that, so a reported side effect from earlier is not
missed. Reviews already screened under the current prompt version are
skipped, so the script can be run again.

    python scripts/screen_app_reviews.py              # count what would be screened
    python scripts/screen_app_reviews.py --apply      # screen them (one model call each)
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="call the model and store findings")
    ap.add_argument("--max-calls", type=int, default=200, help="stop after this many model calls")
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services import brand_screening as bs

    conn = get_database_instance()._temp_get_connection()
    rows = conn.execute(text("""
        SELECT DISTINCT ON (a.uri, c.brand_id) a.uri, c.brand_id, b.display_name,
               a.title, COALESCE(a.summary, '')
          FROM articles a
          JOIN bw_article_categories c ON c.article_uri = a.uri
          JOIN bw_brands b ON b.id = c.brand_id
         WHERE a.news_source IN ('Google Play', 'App Store')
           AND NOT EXISTS (SELECT 1 FROM bw_screening_verdicts v
                            WHERE v.article_uri = a.uri AND v.brand_id = c.brand_id
                              AND v.prompt_version = :pv)
         ORDER BY a.uri, c.brand_id
    """), {"pv": bs.PROMPT_VERSION}).fetchall()
    gated = [r for r in rows
             if bs.RISK_TRIGGER_RE.search(f"{r[3]}. {r[4]}") or bs.HEALTH_TRIGGER_RE.search(f"{r[3]}. {r[4]}")]
    print(f"{len(rows)} app reviews not yet screened under {bs.PROMPT_VERSION}; {len(gated)} match the gate")
    if not args.apply:
        return 0
    calls = flagged = 0
    for uri, bid, name, title, summary in gated:
        if calls >= args.max_calls:
            print(f"stopped at --max-calls {args.max_calls}")
            break
        calls += 1
        risks = await bs.llm_detect_risks(title or "", summary or "", name)
        method = "llm"
        if risks is None:
            risks, method = bs.keyword_risk_fallback(f"{title}. {summary}"), "keyword"
        if risks:
            bs.store_article_risks(conn, uri, bid, risks, method)
            flagged += 1
            for r in risks:
                print(f"  {name}: {r['risk_type']} {r['severity']} — {r.get('justification') or ''}")
        bs.record_verdict(conn, uri, bid, "risk_found" if risks else "no_risk_found", method)
        conn.commit()
    print(f"screened {calls}, flagged {flagged}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
