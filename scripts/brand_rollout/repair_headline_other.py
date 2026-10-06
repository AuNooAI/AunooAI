"""Correct stored brand decisions made wrong by two defects fixed on 6 Oct:
(1) the headline rule lifted a judge's "other" to notable; (2) Pearson's
profile lacked the airport-heist exclusions. A row is changed only if the
current rules say so: its stored judge verdict was "other", or the current
profile marks its mention as a different entity. Every row is backed up first.
Dry run unless --apply."""
import json, os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(".env")
import logging; logging.disable(logging.WARNING)
from sqlalchemy import text
from app.database import get_database_instance
from app.services import brand_profile as bp

apply = "--apply" in sys.argv
site = os.path.basename(os.getcwd()).split('.')[0]
conn = get_database_instance()._temp_get_connection()
rows_b, reg = bp.load_rows(conn)
cands = conn.execute(text("""
  SELECT m.id, m.article_uri, g.topic AS gtopic, m.brand_relation, m.relevance_status, m.decision_evidence,
         a.title, a.summary, a.original_title, a.original_summary, a.news_source, a.topic AS atopic, a.ingest_status
    FROM keyword_article_matches m JOIN keyword_groups g ON g.id = m.group_id JOIN articles a ON a.uri = m.article_uri
   WHERE m.brand_relation IN ('subject','notable')""")).mappings().all()
fix = []
for r in cands:
    ev = r["decision_evidence"] or {}
    why = None
    if ev.get("provenance") == "model+headline" and ev.get("model_label") == "other":
        why = "headline rule overruled the judge's 'other' (fixed 6 Oct, brand-coverage-3)"
    else:
        res = bp.resolve(rows_b, r["gtopic"], None, reg)
        if res.profile is not None and bp.detect_mention(res.profile, dict(r, uri=r["article_uri"])).status == "same_name":
            why = "names a different entity under the current profile (6 Oct exclusions)"
    if why:
        fix.append((r, why))
print(f"{site}: {len(fix)} row(s) to correct")
for r, why in fix:
    print(f"  {r['brand_relation']:8} -> other | article {r['ingest_status']:<18} | {(r['original_title'] or r['title'] or '')[:70]} | {why}")
if apply and fix:
    backup = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r, _ in fix]
    path = f"/var/tmp/brand_rollout/backup/{site}-headline-repair.json"
    json.dump(backup, open(path, "w"), ensure_ascii=False, indent=1, default=str)
    for r, why in fix:
        ev = dict(r["decision_evidence"] or {})
        ev["corrected"] = {"at": "2026-10-06", "from": r["brand_relation"], "why": why}
        conn.execute(text("UPDATE keyword_article_matches SET brand_relation = 'other', relevance_status = 'filtered_relevance', "
                          "decision_evidence = CAST(:e AS jsonb) WHERE id = :id"),
                     {"e": json.dumps(ev, ensure_ascii=False), "id": r["id"]})
        # The article's own verdict follows only when this brand topic owns the
        # article and nothing else admitted it, as the brand path's rejection does.
        conn.execute(text("UPDATE articles SET ingest_status = 'filtered_relevance', topic_alignment_score = 0 "
                          "WHERE uri = :u AND topic = :t AND NOT EXISTS (SELECT 1 FROM keyword_article_matches x "
                          "WHERE x.article_uri = :u AND x.id <> :id AND x.brand_relation IN ('subject','notable','sector'))"),
                     {"u": r["article_uri"], "t": r["gtopic"], "id": r["id"]})
    conn.commit()
    print(f"applied; backup {path}")
conn.close()
