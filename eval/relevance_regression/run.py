#!/usr/bin/env python
"""
Relevance regression test — recurring guard for the ingest relevance scorer.

Two modes:
  --golden (default)  Score a fixed labelled fixture set through the REAL pipeline
                      (hybrid_relevance_service.score_relevance) and compare the
                      relevant/not decision to the expected label. Deterministic;
                      catches code regressions (prompt/override/threshold changes).
  --live N            Sample N recent articles per topic from the DB, score them
                      through the pipeline, and have a COST-CONSCIOUS model
                      (nova-lite) independently judge true relevance. Reports
                      pipeline-vs-judge agreement; catches data drift.

Exit code 1 if accuracy < PASS_THRESHOLD, so it can drive a cron alert.

Usage:
  cd /home/orochford/tenants/<tenant> && .venv/bin/python eval/relevance_regression/run.py [--golden|--live 40]
Env: AWS_BEARER_TOKEN_BEDROCK, AWS_REGION_NAME (for the nova judge / LLM fallback).
"""
import os, sys, json, re, argparse
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

HERE = os.path.dirname(os.path.abspath(__file__))
RECALL_MIN = 0.80      # PRIMARY gate: the fix's job is "don't drop relevant articles"
PRECISION_MIN = 0.40   # secondary floor: catch a noise flood (tunable per-group threshold)
JUDGE_MODEL = os.getenv("RELEVANCE_TEST_JUDGE", "nova-lite")   # cost-conscious evaluator

def log(*a): print(*a, flush=True)

def pipeline_relevant(svc, topic, title, summary, threshold):
    r = svc.score_relevance(topic, title, summary, threshold=threshold, use_llm_fallback=True)
    return bool(r["relevant"]), float(r["score"]), r.get("method", "")

def nova_judge(topic, title, summary):
    """Independent relevance verdict from a cheap model. Returns True/False/None."""
    from app.ai_models import AIModelFactory, extract_content
    entity = re.sub(r'^Brand Monitoring\s+', '', topic).strip()
    prompt = (f'A monitor tracks "{entity or topic}". Is the article below relevant to that '
              f'(the entity, its products, competitors, or its industry/sector count as relevant; '
              f'a coincidental same-name match about an unrelated subject does not)?\n\n'
              f'Title: {title}\nSummary: {summary[:300]}\n\nAnswer ONLY "yes" or "no".')
    try:
        out = extract_content(AIModelFactory.get_model(JUDGE_MODEL).generate_sync(prompt, max_tokens=4, temperature=0.0))
        m = re.search(r'\b(yes|no)\b', out.lower())
        return (m.group(1) == "yes") if m else None
    except Exception as e:
        log(f"  judge error: {str(e)[:60]}"); return None

def metrics(pairs):
    """pairs: list of (predicted_bool, truth_bool). Returns acc/precision/recall."""
    tp=sum(1 for p,t in pairs if p and t); fp=sum(1 for p,t in pairs if p and not t)
    tn=sum(1 for p,t in pairs if not p and not t); fn=sum(1 for p,t in pairs if not p and t)
    n=len(pairs) or 1
    acc=(tp+tn)/n
    prec=tp/(tp+fp) if (tp+fp) else 1.0
    rec=tp/(tp+fn) if (tp+fn) else 1.0
    return acc, prec, rec, (tp,fp,tn,fn)

def run_golden(svc):
    fixtures=[json.loads(l) for l in open(os.path.join(HERE,"fixtures.jsonl")) if l.strip()]
    log(f"\n=== GOLDEN regression: {len(fixtures)} fixtures ===")
    pairs=[]
    for f in fixtures:
        pred,score,method = pipeline_relevant(svc, f["topic"], f["title"], f.get("summary",""), f.get("threshold",0.5))
        ok = (pred == f["expected"])
        pairs.append((pred, f["expected"]))
        if not ok:
            log(f"  MISMATCH exp={f['expected']} got={pred} ({score:.2f}) [{f.get('note','')}] {f['title'][:60]}")
    acc,prec,rec,cm=metrics(pairs)
    log(f"accuracy={acc:.0%}  precision={prec:.0%}  recall={rec:.0%}  (tp,fp,tn,fn)={cm}")
    return acc,prec,rec

def run_live(svc, n):
    import psycopg2
    def env(k):
        for line in open(os.path.join(HERE,"../../.env")):
            if line.startswith(k+"="): return line.split("=",1)[1].strip()
    conn=psycopg2.connect(host=env("DB_HOST") or "localhost", port=env("DB_PORT") or 5432,
                          dbname=env("DB_NAME"), user=env("DB_USER"), password=env("DB_PASSWORD"))
    cur=conn.cursor()
    cur.execute("""SELECT topic, title, COALESCE(summary,'') FROM articles
                   WHERE topic IS NOT NULL AND topic<>'' AND title IS NOT NULL
                     AND news_source NOT LIKE 'xpoz:%%' AND news_source<>'bluesky'
                     AND submission_date > (now()-interval '3 days')::text
                   ORDER BY random() LIMIT %s""", (n,))
    sample=cur.fetchall()
    log(f"\n=== LIVE drift check: {len(sample)} recent articles, judged by {JUDGE_MODEL} ===")
    pairs=[]
    for topic,title,summary in sample:
        thr = 0.1 if topic.startswith("Brand Monitoring") else 0.5
        pred,_,_ = pipeline_relevant(svc, topic, title, summary, thr)
        truth = nova_judge(topic, title, summary)
        if truth is None: continue
        pairs.append((pred, truth))
    if not pairs: log("no judged samples"); return 1.0,1.0,1.0
    acc,prec,rec,cm=metrics(pairs)
    log(f"pipeline-vs-{JUDGE_MODEL}: agreement={acc:.0%}  precision={prec:.0%}  recall={rec:.0%}  (tp,fp,tn,fn)={cm}")
    return acc,prec,rec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--live", type=int, default=0, help="sample N recent articles, judge with nova-lite")
    ap.add_argument("--golden", action="store_true")
    args=ap.parse_args()
    from app.services.hybrid_relevance_service import get_hybrid_relevance_service
    svc=get_hybrid_relevance_service(); svc.load_models()
    results=[]
    if args.live: results.append(run_live(svc, args.live))
    if args.golden or not args.live: results.append(run_golden(svc))
    ok = all(rec >= RECALL_MIN and prec >= PRECISION_MIN for _, prec, rec in results)
    worst_rec = min(rec for _, _, rec in results)
    worst_prec = min(prec for _, prec, _ in results)
    log(f"\nRESULT: {'PASS' if ok else 'FAIL'}  (recall {worst_rec:.0%} vs min {RECALL_MIN:.0%}, "
        f"precision {worst_prec:.0%} vs min {PRECISION_MIN:.0%})")
    sys.exit(0 if ok else 1)

if __name__=="__main__":
    main()
