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

def env(k):
    for line in open(os.path.join(HERE, "../../.env")):
        if line.startswith(k + "="): return line.split("=", 1)[1].strip()
    return None

def db_conn():
    import psycopg2
    return psycopg2.connect(host=env("DB_HOST") or "localhost", port=env("DB_PORT") or 5432,
                            dbname=env("DB_NAME"), user=env("DB_USER"), password=env("DB_PASSWORD"))

def log_run(mode, acc, prec, rec, cm, n):
    """Append this run's metrics to relevance_test_runs so precision/recall can be
    trended over time. Self-creating harness table (test tooling, not app schema),
    so it stays outside alembic. Never fails the test — logging is best-effort."""
    tp, fp, tn, fn = cm
    passed = rec >= RECALL_MIN and prec >= PRECISION_MIN
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS relevance_test_runs (
            id serial PRIMARY KEY, run_at timestamptz NOT NULL DEFAULT now(),
            mode text NOT NULL, n_items int, acc real, prec real, rec real,
            tp int, fp int, tn int, fn int, passed boolean)""")
        cur.execute("""INSERT INTO relevance_test_runs
            (mode, n_items, acc, prec, rec, tp, fp, tn, fn, passed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (mode, n, round(acc, 4), round(prec, 4), round(rec, 4), tp, fp, tn, fn, passed))
        conn.commit(); cur.close(); conn.close()
        log(f"  -> logged to relevance_test_runs (mode={mode}, passed={passed})")
    except Exception as e:
        log(f"  (db trend-log skipped: {str(e)[:70]})")

def _threshold_resolver():
    """Return a fn topic->effective threshold, matching production (keyword_groups
    min_relevance_threshold, fallback global). Empty resolver if DB unreachable."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT name, min_relevance_threshold FROM keyword_groups")
        groups = [(nm, t) for nm, t in cur.fetchall()]
        cur.execute("SELECT min_relevance_threshold FROM keyword_monitor_settings WHERE id=1")
        r = cur.fetchone(); g = float(r[0]) if r and r[0] is not None else 0.5
        cur.close(); conn.close()
    except Exception:
        groups, g = [], 0.5
    def resolve(topic):
        if topic.startswith("Brand Monitoring"):
            e = topic[len("Brand Monitoring"):].strip().lower()
            for nm, t in groups:
                nl = (nm or "").strip().lower()
                if "brand watch" in nl and e and nl.startswith(e):
                    return float(t) if t is not None else g
        else:
            tl = topic.strip().lower()
            for nm, t in groups:
                if (nm or "").strip().lower() == tl:
                    return float(t) if t is not None else g
        return g
    return resolve

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
    log_run("golden", acc, prec, rec, cm, len(fixtures))
    return acc,prec,rec

def run_live(svc, n):
    resolve_thr = _threshold_resolver()
    conn=db_conn(); cur=conn.cursor()
    cur.execute("""SELECT topic, title, COALESCE(summary,'') FROM articles
                   WHERE topic IS NOT NULL AND topic<>'' AND title IS NOT NULL
                     AND news_source NOT LIKE 'xpoz:%%' AND news_source<>'bluesky'
                     AND submission_date > (now()-interval '3 days')::text
                   ORDER BY random() LIMIT %s""", (n,))
    sample=cur.fetchall(); cur.close(); conn.close()
    log(f"\n=== LIVE drift check: {len(sample)} recent articles, judged by {JUDGE_MODEL} ===")
    pairs=[]
    for topic,title,summary in sample:
        pred,_,_ = pipeline_relevant(svc, topic, title, summary, resolve_thr(topic))
        truth = nova_judge(topic, title, summary)
        if truth is None: continue
        pairs.append((pred, truth))
    if not pairs: log("no judged samples"); return 1.0,1.0,1.0
    acc,prec,rec,cm=metrics(pairs)
    log(f"pipeline-vs-{JUDGE_MODEL}: agreement={acc:.0%}  precision={prec:.0%}  recall={rec:.0%}  (tp,fp,tn,fn)={cm}")
    log_run("live", acc, prec, rec, cm, len(pairs))
    return acc,prec,rec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--live", type=int, default=0, help="sample N recent articles, judge with nova-lite")
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--trend", type=int, default=0, help="print the last N logged runs and exit")
    args=ap.parse_args()
    if args.trend:
        try:
            conn=db_conn(); cur=conn.cursor()
            cur.execute("""SELECT run_at, mode, n_items, acc, prec, rec, passed
                           FROM relevance_test_runs ORDER BY run_at DESC LIMIT %s""", (args.trend,))
            rows=cur.fetchall(); cur.close(); conn.close()
            log(f"{'run_at (UTC)':19}  {'mode':6} {'n':>3} {'acc':>5} {'prec':>5} {'rec':>5}  pass")
            for run_at, mode, n, acc, prec, rec, passed in rows:
                log(f"{str(run_at)[:19]:19}  {mode:6} {n or 0:3d} {acc or 0:5.2f} {prec or 0:5.2f} {rec or 0:5.2f}  {'Y' if passed else 'N'}")
        except Exception as e:
            log(f"trend query failed (no runs logged yet?): {str(e)[:80]}")
        sys.exit(0)
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
