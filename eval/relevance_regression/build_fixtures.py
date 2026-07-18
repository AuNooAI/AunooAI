#!/usr/bin/env python
"""
Seed per-tenant golden fixtures for the relevance regression test.

Samples recent articles from THIS tenant's DB across its brand + general topics,
labels each with a cost-conscious model (nova-lite) as the ground truth, and writes
fixtures.jsonl. Run once per tenant (and re-run to refresh):

  cd /home/orochford/tenants/<tenant> && \
  AWS_BEARER_TOKEN_BEDROCK=$AWS_BEDROCK_API_KEY PYTHONPATH=$PWD \
  .venv/bin/python eval/relevance_regression/build_fixtures.py

Fixtures are tenant-local because a brand/topic on one tenant may not exist on another.
"""
import os, re, json, sys
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1"); os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
import psycopg2
HERE = os.path.dirname(os.path.abspath(__file__))
# Ground-truth LABELS are worth a stronger model — this is a one-time (per-reseed) cost.
# The recurring run.py --live judge and the in-pipeline fallback stay on cheap nova-lite;
# only fixture labelling uses the better model. nova-lite mislabels obvious cases (marked
# clear Geopolitical news "not relevant"), which poisoned the golden set.
JUDGE = os.getenv("RELEVANCE_TEST_LABELER", "nova-pro")
PER_TOPIC = 6      # candidate articles sampled per topic (before balancing)
CAP_PER_CLASS = 15 # keep at most this many relevant / not-relevant in the balanced set

def env(k):
    for line in open(os.path.join(HERE, "../../.env")):
        if line.startswith(k + "="): return line.split("=", 1)[1].strip()

def judge(topic, title, summary):
    from app.ai_models import AIModelFactory, extract_content
    entity = re.sub(r'^Brand Monitoring\s+', '', topic).strip()
    p = (f'A monitor tracks "{entity or topic}". Is the article relevant to it (the entity, its '
         f'products, competitors, or its industry/sector count; a coincidental same-name match about '
         f'an unrelated subject does not)?\nTitle: {title}\nSummary: {summary[:300]}\nAnswer ONLY "yes" or "no".')
    out = extract_content(AIModelFactory.get_model(JUDGE).generate_sync(p, max_tokens=4, temperature=0.0))
    m = re.search(r'\b(yes|no)\b', out.lower())
    return None if not m else (m.group(1) == "yes")

def main():
    conn = psycopg2.connect(host=env("DB_HOST") or "localhost", port=env("DB_PORT") or 5432,
                            dbname=env("DB_NAME"), user=env("DB_USER"), password=env("DB_PASSWORD"))
    cur = conn.cursor()
    # topics that actually have recent news on this tenant
    cur.execute("""SELECT topic, count(*) FROM articles
                   WHERE topic IS NOT NULL AND topic<>'' AND news_source NOT LIKE 'xpoz:%%'
                     AND news_source<>'bluesky' AND submission_date > (now()-interval '14 days')::text
                   GROUP BY topic HAVING count(*) >= 5 ORDER BY 2 DESC LIMIT 12""")
    topics = [r[0] for r in cur.fetchall()]
    fixtures = []
    for topic in topics:
        thr = 0.1 if topic.startswith("Brand Monitoring") else 0.5
        cur.execute("""SELECT title, COALESCE(summary,'') FROM articles
                       WHERE topic=%s AND title IS NOT NULL AND news_source NOT LIKE 'xpoz:%%'
                         AND news_source<>'bluesky' AND submission_date > (now()-interval '14 days')::text
                       ORDER BY random() LIMIT %s""", (topic, PER_TOPIC))
        for title, summary in cur.fetchall():
            try:
                truth = judge(topic, title, summary)
            except Exception as e:
                print(f"  judge error ({str(e)[:40]}) — skipping"); truth = None
            if truth is None: continue
            fixtures.append(dict(topic=topic, threshold=thr, title=title,
                                 summary=summary[:400], expected=truth, note="auto/"+JUDGE))
    # Balance the set: equal relevant / not-relevant (capped) so accuracy & recall are
    # meaningful. Random firehose sampling is ~90% noise, which would otherwise swamp
    # the metric and hide relevant-article regressions.
    pos = [f for f in fixtures if f["expected"]]
    neg = [f for f in fixtures if not f["expected"]]
    n = min(len(pos), len(neg), CAP_PER_CLASS)
    if n >= 3:
        balanced = pos[:n] + neg[:n]
    else:
        balanced = fixtures  # too few of one class to balance — keep everything, note it
    out = os.path.join(HERE, "fixtures.jsonl")
    open(out, "w").write("\n".join(json.dumps(f) for f in balanced) + "\n")
    bp = sum(1 for f in balanced if f["expected"])
    print(f"labeled {len(fixtures)} (pos={len(pos)} neg={len(neg)}); wrote {len(balanced)} balanced "
          f"fixtures ({bp} relevant / {len(balanced)-bp} not) across {len(topics)} topics -> {out}")

if __name__ == "__main__":
    main()
