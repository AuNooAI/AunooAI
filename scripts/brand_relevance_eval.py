#!/usr/bin/env python3
"""Small reviewed samples for brand relevance, and their precision and recall.

docs/BRAND_RELEVANCE_SPEC.md, "Validation without a large annotation project".

    sample  draw a stratified sample of one brand topic's news candidates and
            write <out>/<site>-<brand>-<date>.json plus a review page (.html).
            A person opens the page, answers one question per row and saves
            the answers as <...>.reviews.json.
    score   compare the system's decisions with the reviewed answers.

The review question is: does this article belong in independent coverage of
this brand? Answers: coverage, sector, owned, not_coverage, cannot_tell.
The script never fills in an answer; model output is not ground truth.

Strata (each sampled separately, so rare cases are seen; rates are weighted
back by population): included (earned), owned, sector, rejected that names
the brand, rejected that does not, and undecided (unavailable or deferred).

Precision = TP / (TP + FP) over rows the system counts as earned; recall =
TP / (TP + FN) over rows reviewed as coverage. Both are reported weighted by
stratum population and unweighted with a 95% Wilson interval. A missing
denominator prints "unavailable". This measures the collected candidates of
the sampled window only: it says nothing about stories the collectors never
found, and replaying an old sample is a regression check, not this week's
accuracy.

    cd /home/orochford/tenants/sunstar.aunoo.ai
    .venv/bin/python scripts/brand_relevance_eval.py sample --brand "Colgate-Palmolive" --n 20 --out eval/brand_relevance/reviews
    .venv/bin/python scripts/brand_relevance_eval.py score eval/brand_relevance/reviews/sunstar-colgate-palmolive-2026-10-06.json
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ANSWERS = ("coverage", "sector", "owned", "not_coverage", "cannot_tell")
STRATA = ("included", "owned", "sector", "rejected_named", "rejected_unnamed", "undecided")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def stratum(row, named: bool) -> str:
    rel, src, status = row.get("brand_relation"), row.get("source_relation"), row.get("relevance_status")
    if status in ("relevance_check_failed", "deferred") and rel is None:
        return "undecided"
    if rel is not None:
        if src == "owned" and rel in ("subject", "notable", "sector"):
            return "owned"
        if rel in ("subject", "notable") and src == "independent":
            return "included"
        if rel == "sector":
            return "sector"
        return "rejected_named" if named else "rejected_unnamed"
    # Legacy rows: the article's own verdict.
    if row.get("ingest_status") == "approved":
        return "included"
    return "rejected_named" if named else "rejected_unnamed"


def system_counts_as_earned(s: str) -> bool:
    return s == "included"


def cmd_sample(args) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services import brand_profile as bp
    from app.services.brand_coverage import brand_topics
    conn = get_database_instance()._temp_get_connection()
    try:
        res = bp.resolve_for_topic(conn, f"Brand Monitoring {args.brand}")
        if res.profile is None:
            print(f"No single enabled profile for {args.brand!r}: {res.error or 'not found'}")
            return 2
        prof = res.profile
        cols = {c for (c,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='keyword_article_matches'"))}
        lab = ("m.brand_relation, m.source_relation, m.relevance_status" if "brand_relation" in cols
               else "NULL AS brand_relation, NULL AS source_relation, NULL AS relevance_status")
        rows = [dict(r) for r in conn.execute(text(f"""
            SELECT DISTINCT ON (a.uri) a.uri, a.title, a.summary, a.original_title, a.original_summary,
                   a.news_source, a.ingest_status, {lab}
              FROM keyword_article_matches m JOIN keyword_groups g ON g.id = m.group_id
              JOIN articles a ON a.uri = m.article_uri
             WHERE g.topic = ANY(:t) AND (a.social_meta IS NULL OR a.social_meta::text = 'null')
               AND left(a.submission_date, 10) >= to_char(now() - make_interval(days => :d), 'YYYY-MM-DD')
             ORDER BY a.uri
        """), {"t": brand_topics(prof.display_name), "d": int(args.days)}).mappings()]
    finally:
        conn.close()
    population = {s: [] for s in STRATA}
    for r in rows:
        named = bp.detect_mention(prof, r).verified
        population[stratum(r, named)].append(r)
    rng = random.Random(args.seed)
    per = max(1, args.n // max(1, sum(1 for s in STRATA if population[s])))
    sample = []
    for s in STRATA:
        pick = rng.sample(population[s], min(per, len(population[s])))
        for r in pick:
            sample.append({"uri": r["uri"], "title": r["original_title"] or r["title"], "title_en": r["title"],
                           "summary": (r["summary"] or "")[:600], "source": r["news_source"], "stratum": s,
                           "system_earned": system_counts_as_earned(s),
                           "brand_relation": r.get("brand_relation"), "source_relation": r.get("source_relation")})
    site = os.path.basename(os.getcwd()).replace(".aunoo.ai", "")
    base = f"{site}-{_slug(prof.display_name)}-{date.today().isoformat()}"
    os.makedirs(args.out, exist_ok=True)
    meta = {"site": site, "brand": prof.display_name, "brand_id": prof.brand_id, "profile_version": prof.version,
            "window_days": int(args.days), "drawn": date.today().isoformat(), "seed": args.seed,
            "population": {s: len(population[s]) for s in STRATA},
            "sampling": f"up to {per} rows per non-empty stratum, uniformly at random within it",
            "rows": sample}
    jpath = os.path.join(args.out, base + ".json")
    json.dump(meta, open(jpath, "w"), ensure_ascii=False, indent=1)
    hpath = os.path.join(args.out, base + ".html")
    open(hpath, "w").write(review_page(meta, base + ".reviews.json"))
    print(f"{len(sample)} rows sampled from {len(rows)} candidates: {meta['population']}")
    print(f"Sample: {jpath}\nReview page: {hpath} (save answers as {base}.reviews.json next to it)")
    return 0


def review_page(meta, out_name: str) -> str:
    items = []
    for i, r in enumerate(meta["rows"]):
        opts = "".join(f'<label><input type="radio" name="r{i}" value="{a}"> {a.replace("_", " ")}</label> ' for a in ANSWERS)
        en = f'<div class="en">{html.escape(r["title_en"] or "")}</div>' if r["title_en"] and r["title_en"] != r["title"] else ""
        items.append(f'<li data-uri="{html.escape(r["uri"])}"><a href="{html.escape(r["uri"])}" target="_blank">'
                     f'{html.escape(r["title"] or r["uri"])}</a>{en}<div class="src">{html.escape(r["source"] or "")}</div>'
                     f'<div class="sum">{html.escape(r["summary"] or "")}</div><div class="opts">{opts}</div></li>')
    return f"""<!doctype html><meta charset="utf-8"><title>Brand review: {html.escape(meta['brand'])}</title>
<style>body{{font:15px system-ui;max-width:900px;margin:2em auto;padding:0 16px}}li{{margin:1em 0;padding-bottom:1em;border-bottom:1px solid #ddd}}
.src,.en{{color:#666;font-size:13px}}.sum{{font-size:13px;margin:.3em 0}}label{{margin-right:1em}}</style>
<h1>Does this article belong in independent coverage of {html.escape(meta['brand'])}?</h1>
<p>coverage: independent reporting where {html.escape(meta['brand'])} is the subject or plays a real part.
sector: about its market, without it playing a part. owned: published by {html.escape(meta['brand'])} itself.
not coverage: anything else. cannot tell: not enough to decide. The rows are in random order within groups;
the system's own decision is not shown.</p><ol>{''.join(items)}</ol>
<button onclick="save()">Save answers</button>
<script>function save(){{const out={{brand:{json.dumps(meta['brand'])},answers:{{}}}};
document.querySelectorAll('li').forEach((li,i)=>{{const c=li.querySelector('input:checked');if(c)out.answers[li.dataset.uri]=c.value;}});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{{type:'application/json'}}));
a.download={json.dumps(out_name)};a.click();}}</script>"""


def wilson(k: int, n: int):
    if n == 0:
        return None
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - m) / d), min(1.0, (c + m) / d))


def score(meta, answers):
    pop = meta["population"]
    by_stratum = {}
    for r in meta["rows"]:
        by_stratum.setdefault(r["stratum"], []).append(r)
    tp = fp = fn = tn = 0
    wtp = wfp = wfn = 0.0
    unanswered = cannot = 0
    for s, rs in by_stratum.items():
        w = pop.get(s, 0) / len(rs) if rs else 0
        for r in rs:
            a = answers.get(r["uri"])
            if a is None:
                unanswered += 1
                continue
            if a == "cannot_tell":
                cannot += 1
                continue
            truth = a == "coverage"
            sys_ = r["system_earned"]
            if sys_ and truth:
                tp += 1; wtp += w
            elif sys_ and not truth:
                fp += 1; wfp += w
            elif truth:
                fn += 1; wfn += w
            else:
                tn += 1
    undecided_pop = pop.get("undecided", 0)
    total_pop = sum(pop.values())

    def rate(a, b):
        return a / (a + b) if (a + b) else None
    return {
        "counts": {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "cannot_tell": cannot, "unanswered": unanswered},
        "precision": rate(tp, fp), "precision_ci": wilson(tp, tp + fp),
        "recall": rate(tp, fn), "recall_ci": wilson(tp, tp + fn),
        "precision_weighted": rate(wtp, wfp), "recall_weighted": rate(wtp, wfn),
        "availability": (1 - undecided_pop / total_pop) if total_pop else None,
        "population": pop,
    }


def _fmt(x):
    return "unavailable" if x is None else f"{x:.2f}"


def cmd_score(args) -> int:
    meta = json.load(open(args.sample))
    rpath = args.reviews or args.sample.replace(".json", ".reviews.json")
    if not os.path.exists(rpath):
        print(f"No reviews at {rpath}: precision and recall are unavailable until a person answers the sheet.")
        return 1
    answers = json.load(open(rpath)).get("answers", {})
    s = score(meta, answers)
    c = s["counts"]
    print(f"{meta['site']} / {meta['brand']} — {meta['window_days']}-day window drawn {meta['drawn']}, "
          f"{len(meta['rows'])} rows sampled ({meta['sampling']})")
    print(f"TP {c['TP']}  FP {c['FP']}  FN {c['FN']}  TN {c['TN']}  cannot tell {c['cannot_tell']}  unanswered {c['unanswered']}")
    ci = lambda t: "" if not t else f" (95% interval {t[0]:.2f}–{t[1]:.2f})"
    print(f"Precision {_fmt(s['precision'])}{ci(s['precision_ci'])}; weighted by stratum {_fmt(s['precision_weighted'])}")
    print(f"Recall    {_fmt(s['recall'])}{ci(s['recall_ci'])}; weighted by stratum {_fmt(s['recall_weighted'])}")
    print(f"Decided (not unavailable or deferred): {_fmt(s['availability'])} of {sum(s['population'].values())} candidates")
    print("This covers collected candidates in the window only, not stories the collectors never found.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("sample")
    a.add_argument("--brand", required=True)
    a.add_argument("--n", type=int, default=20)
    a.add_argument("--days", type=int, default=30)
    a.add_argument("--seed", type=int, default=20261006)
    a.add_argument("--out", default="eval/brand_relevance/reviews")
    b = sub.add_parser("score")
    b.add_argument("sample")
    b.add_argument("--reviews")
    args = ap.parse_args()
    return cmd_sample(args) if args.cmd == "sample" else cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
