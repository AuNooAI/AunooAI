"""Run the new brand decision on reviewed sample rows and score old and new against the reviewer.

Run from the site tree: .venv/bin/python scripts/brand_relevance_compare.py <reviews dir> <site>
Articles that never name the brand go to the site topic rules on the live path; here the stored
old verdict stands in for those rules, so the comparison isolates the brand decision itself.
--policy applies the reviewer's 6 Oct policy answers: valuation pages are not coverage, and an
article that never names the brand is at most sector."""
import glob, json, os, re, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(".env")
import logging; logging.disable(logging.WARNING)
from sqlalchemy import text
from app.database import get_database_instance
from app.services import brand_profile as bp, brand_decision as bd
R, site = sys.argv[1], sys.argv[2]
POLICY = "--policy" in sys.argv[3:]
adjusted = []
ans = json.load(open(f"{R}/{site}-reviews-2026-10-06.json"))["answers"]
conn = get_database_instance()._temp_get_connection(); rows_b, reg = bp.load_rows(conn)
judges = bd.configured_judges(); out = []
tot = {"old": [0,0,0,0], "new": [0,0,0,0]}
for p in sorted(glob.glob(f"{R}/{site}-*-2026-10-06.json")):
    if re.search(r"-reviews?-2026", p): continue
    m = json.load(open(p)); per = {"old": [0,0,0,0], "new": [0,0,0,0]}
    for r in m["rows"]:
        a = ans.get(r["uri"])
        if a in (None, "cannot_tell"): continue
        art = conn.execute(text("SELECT uri,title,summary,original_title,original_summary,news_source,bias_source,topic FROM articles WHERE uri=:u"), {"u": r["uri"]}).mappings().first()
        res = bp.resolve(rows_b, "Brand Monitoring " + m["brand"], None, reg)
        if POLICY and a == "coverage":
            # Reviewer's policy answers (6 Oct): valuation pages are never
            # coverage, and an article that never names the brand is at most
            # sector, whatever its theme.
            ex = bp.exclusion(res.profile, dict(art))
            if ex and ex[0] == "valuation_page":
                a = "not_coverage"; adjusted.append(f"  valuation page -> not coverage | {(art['title'] or '')[:70]}")
            elif bp.detect_mention(res.profile, dict(art)).status == "none":
                a = "sector"; adjusted.append(f"  brand not named -> sector      | {(art['title'] or '')[:70]}")
        truth = a == "coverage"
        old0 = r["stratum"] == "included"
        d = bd.decide(res, dict(art), judges=judges, topic_scorer=lambda _a, _o=old0: _o, reuse=None)
        new = bool(d and d.earned); old = r["stratum"] == "included"
        for k, pred in (("old", old), ("new", new)):
            i = (0 if truth else 1) if pred else (2 if truth else 3)   # TP FP FN TN
            per[k][i] += 1; tot[k][i] += 1
        if new != truth or old != truth:
            out.append(f"  {m['brand'][:12]:12} you={a:12} old={'in' if old else 'out':3} new={(d.brand_relation or d.outcome) if d else 'none':10} src={d.source_relation if d else '':11} | {(art['original_title'] or art['title'] or '')[:75]}")
    print(f"{m['brand']:18} old TP/FP/FN/TN {per['old']}   new {per['new']}")
def pr(v):
    tp, fp, fn, tn = v; return f"precision {tp/(tp+fp) if tp+fp else float('nan'):.2f}, recall {tp/(tp+fn) if tp+fn else float('nan'):.2f}"
print(f"\nALL old: {tot['old']} {pr(tot['old'])}\nALL new: {tot['new']} {pr(tot['new'])}\n\nRows where old or new disagrees with the reviewer:")
print("\n".join(out))
if adjusted:
    print("\nAnswers adjusted to the policy:"); print("\n".join(adjusted))
