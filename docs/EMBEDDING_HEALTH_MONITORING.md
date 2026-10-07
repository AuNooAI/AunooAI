# Embedding health monitoring — what to check and why

**Status (checked 2026-10-07):** checks A–D are built and running (`scripts/embedding_health_check.sh`,
deployed as `/home/orochford/bin/embedding_health_check.sh`, root crontab `15,45 * * * *`) on all
eight running sites. Checks E–I are specification only. Nothing retries a missing embedding
automatically; see "What happens today when an embedding fails" below.
**Written:** 2026-08-02, after wbm spent four weeks writing no embeddings without anyone noticing.

## Why this exists

On 2026-07-05 wbm's `articles.embedding` column became `vector(768)` while its code still
produced 1536-d vectors. Every write raised `expected 768 dimensions, not 1536`. That continued
until 2026-08-02, when it was found by accident while fact-checking an unrelated line in
`AI_DESIGN_PATTERNS.md`. In that window 26,348 articles were collected and none were indexed.

Nothing alerted. The reasons are worth stating, because they determine what a useful check looks
like:

1. **The loud parts kept working.** Collection ran, enrichment ran, brand alerts fired every week.
   `collector_health_check.sh` watches collection volume and the keyword-monitor heartbeat, and
   both were healthy the entire time. A check on "is the system doing things" cannot catch this.
2. **The failure was per-article and non-fatal.** Each upsert logged an ERROR and moved on. No
   crash, no restart loop, no queue backing up visibly.
3. **The downstream consumer fails silently by design.** `brand_watcher_stories.py:15` — "Articles
   without an embedding are simply never written here." Story clustering did not error; it just
   stopped growing.
4. **Search degraded into something plausible.** Queries still returned articles. They were just
   never newer than 5 July.

The general shape: a write path that fails per-item, and read paths that treat missing data as
absence rather than as an error. Any check has to look at the data, not at whether the process is
alive.

## Design principles

**Prefer invariants over rates.** "Code dimension equals column dimension" is either true or
false, has no baseline, and cannot false-positive. "Fewer embeddings than usual today" needs a
baseline, drifts with volume, and cries wolf. Build the invariant checks first — they are cheap
and they would have caught this outage within 30 minutes.

**Do not alert on the relevance gate.** Live ingest only indexes articles it approved, after the
relevance check. (The quality step in between is a placeholder that always approves,
`_quality_check_article_async` in `app/services/automated_ingest_service.py:1657-1664`.) On 2026-08-02 wbm logged `processed: 2, enriched: 2, relevant: 0, saved: 0,
vector_indexed: 0` — that is the filter working, not a fault, and 160 articles legitimately sat
unindexed. A naive "articles collected but not embedded" alert fires constantly on this. See
check E for the way around it.

**Watch the canary, not just the source.** Story-clustering freshness (check G) is a downstream
signal that catches embedding failures, relevance-gate misconfiguration, and clustering bugs
alike, without knowing which. It lags by about a week — clustering ran until 13 July on backlog —
so it is a backstop, not a primary.

**Cover every tenant.** `collector_health_check.sh` originally read
`TENANTS="bugfixing wileytest wiley"` — wbm, the tenant that broke, was the one not being
watched. Fixed 2026-08-02: wbm was added there with a measured floor of 20 articles/12h, and
`embedding_health_check.sh` covers all four from the start.

**The gap reopened and was closed again on 2026-10-07.** Four tenants started after August, abm,
oviva, panaya and sunstar, ran the same 768-d encoder without being checked. Commit `679ee413`
(7 October 2026) added them, and both copies of the script now read
`TENANTS="bugfixing wileytest wiley wbm abm oviva panaya sunstar"` (line 39). The 10:45 run on
7 October logged an OK line for all eight in `/var/log/aunoo-embedding-health.log`.

## What happens today when an embedding fails

Checked against commit `83fecd57` on 2026-10-07.

- **Live ingest.** After an approved save, ingest calls `upsert_article_async` with a 30-second
  timeout (`app/services/automated_ingest_service.py:1456-1465`). When the encoder is down,
  `upsert_article_async` catches the error and only logs "Async vector upsert failed"
  (`app/vector_store_pgvector.py:299-337`). The article stays approved with `embedding` NULL. The
  batch result still counts it in `vector_indexed` (`automated_ingest_service.py:1867-1869`), so
  run counters overstate indexing during an outage.
- **Manual research** (`app/bulk_research.py:645-669`) uses the sync `upsert_article`, which also
  catches and logs. The row stays NULL.
- **Nothing retries.** No scheduled job re-embeds approved rows with a NULL embedding.
  `app/tasks/embedding_backfill.py` has a loop for it, but nothing in `app/` or `scripts/` starts
  it. Automatic retry is work package WP5b in `docs/pipelines/08_INGEST_FIX_SPEC.md` and is not
  built.

### Manual repair after an outage

1. Confirm the encoder answers (check B's `curl`).
2. Count what was missed:
   ```sql
   SELECT count(*) FROM articles WHERE ingest_status = 'approved' AND embedding IS NULL;
   ```
3. From the tenant directory, run the one-shot backfill:
   ```bash
   .venv/bin/python -c "import asyncio; from app.tasks.embedding_backfill import backfill_embeddings; print(asyncio.run(backfill_embeddings(limit=1000)))"
   ```
   It takes every NULL row newest `submission_date` first, whatever its `ingest_status`, so it
   also embeds rejected and social rows, and it embeds title plus summary only, not the tags and
   page text that ingest uses. On a tenant with many unembedded rejected rows, raise `limit` or
   expect the approved rows to wait.
4. Check the column, fill rate and index:
   `.venv/bin/python scripts/embedding_768_postbackfill.py --check`.

## The checks

Ordered by signal quality. A–D are invariants and are the ones now built.

One implementation note learned the hard way on 2026-08-02: `psql` renders `boolean::text` as
`true`/`false` on this box, not `t`/`f`. The first version of check D compared against `t`, so
every healthy index looked like a query failure and the monitor emailed four false alarms on its
first live run. Test a new check in a sandbox — email disabled, own log and state directory —
before letting it reach the real alerting path.

### A. Code and column agree on dimension
**Severity: critical. No false positives. This alone catches the wbm outage.**

Compare the encoder's output width against the database column:

```sql
SELECT format_type(atttypid, atttypmod) FROM pg_attribute
WHERE attrelid = 'articles'::regclass AND attname = 'embedding';
```

against `EMBEDDING_DIM` in that tenant's `app/vector_store_pgvector.py` — 768 on all eight
checked sites (health log, 2026-10-07 10:45). Read it from the file rather than hardcoding it, so
the check keeps working through the next migration. Alert on any mismatch.

Also worth comparing across the two derived centroid columns, which must match:
`emerging_topics.centroid_embedding`, `cluster_snapshots.centroid_embedding`.

### B. The encoder service answers, and answers at the right width
**Severity: critical.**

```bash
curl -s -m 10 -X POST http://localhost:8001/encode \
  -H 'Content-Type: application/json' \
  -d '{"title":"healthcheck","description":"","content":"probe"}'
```

Alert if unreachable, if the response has no `embedding`, or if its length is not `EMBEDDING_DIM`.
All eight sites share this one service (`deberta-encoder.service`), so a single failure here stops
embedding everywhere. The encoder client raises rather than falling back, so an outage means
articles go unindexed, not that bad vectors get written. Those articles are not retried later
(see below).

### C. Vector-write errors in the journal
**Severity: critical. This is the direct symptom.**

```bash
journalctl -u <tenant>.aunoo.ai.service --since "-40min" \
  | grep -cE "vector upsert failed|expected [0-9]+ dimensions|DeBERTa encoder unreachable"
```

Alert on any non-zero count. During the outage this produced several errors per minute
continuously — there is no ambiguity to tune around.

Two failures this pattern does not match, because `grep -E` is case-sensitive here
(`scripts/embedding_health_check.sh:229-230`): the 30-second ingest timeout logs "Vector indexing
timed out" (a warning), and the sync path used by manual research logs "Vector upsert failed" with
a capital V. An unreachable encoder still shows up, because the client logs "DeBERTa encoder
unreachable" first. A hung encoder that never answers can produce only the timeout line.

### D. The HNSW index exists and is valid
**Severity: high. Silent performance failure.**

```sql
SELECT c.relname, i.indisvalid FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'articles_embedding_hnsw_idx';
```

Alert if the row is missing, or if `indisvalid` is false. A failed `CREATE INDEX CONCURRENTLY`
leaves an invalid index behind that the planner ignores, so searches silently fall back to
sequential scans over half a million rows. Nothing errors; queries just get slow.

Current sizes, measured 2026-08-02 with all four backfills complete: bugfixing 740 MB / 193k
rows, wiley 1,026 MB / 265k, wbm 1,943 MB / 514k, wileytest 2,056 MB / 538k.

### E. Embedding freshness, gated on qualifying articles
**Severity: high. Needs care to avoid the relevance-gate false positive.**

The naive version — "newest embedded row is older than N hours" — fires whenever the relevance
filter has a quiet spell. Compare like with like instead: among articles that **passed** the
gates, how many lack an embedding?

```sql
SELECT count(*) FROM articles
WHERE submission_date::timestamp > now() - interval '24 hours'
  AND <gate-passed predicate>
  AND embedding IS NULL;
```

The gate-passed predicate is now known: live ingest embeds only rows it saved with
`ingest_status = 'approved'`, so the check is
`ingest_status = 'approved' AND embedding IS NULL`. Use the time the row was approved, not
`submission_date`, once such a column exists; an old article approved today would otherwise look
overdue or be missed. Measured on bugfixing on 2026-10-07: 2 of 4,896 approved rows first seen in
the last 30 days had no embedding, and 2 of 47,483 approved rows of any age. **Check E is still
not built.** It is part of work package WP5b in `docs/pipelines/08_INGEST_FIX_SPEC.md`. Until
then, C covers the same ground more bluntly.

### F. The NULL backlog is growing
**Severity: medium. Slow-burn detector.**

Record `count(*) WHERE embedding IS NULL` once an hour. Alert if it rises monotonically for 24
hours. During the outage this climbed steadily from zero to 26,348 over four weeks — obvious in
hindsight, invisible without a recorded series.

Needs a small state table or a file under `STATE_DIR`, in the style
`collector_health_check.sh` already uses for alert suppression.

### G. Story clustering has not stalled (Brand Watcher tenants)
**Severity: medium. Downstream canary.**

```sql
SELECT max(created_at) FROM bw_article_stories;
```

Alert if older than roughly 48 hours on a tenant that is actively collecting. During the outage
this froze at 13 July, eight days after the cause, because clustering drained the already-embedded
backlog first. That lag makes it a backstop rather than a primary signal.

Applies to wbm and any other Brand Watcher tenant. Threshold needs a baseline — clustering
cadence has not been measured.

### H. Enrichment has not stalled
**Severity: medium. Adjacent, found while investigating.**

```sql
SELECT max(submission_date) FROM articles WHERE category IS NOT NULL;
```

On wbm this last advanced at 13:09 on 2026-08-02, several hours before anyone looked, and only
11 of 345 articles collected that day were enriched. That may be normal for a brand-monitoring
tenant with tight filters, or it may be a second stall. **Unverified — needs a baseline before a
threshold can be set.** Flagged here so it is not lost.

### I. Duplicate vectors
**Severity: medium. Catches the original corruption class.**

```sql
SELECT count(*) - count(DISTINCT embedding::text) FROM articles WHERE embedding IS NOT NULL;
```

The 2026-06 migration was prompted by one real vector shared across 11,336 unrelated articles,
which no cosine threshold can separate. Post-migration wileytest measured 94% distinct with a
max duplicate group of 55, and that 55 was a genuinely re-ingested identical article. Alert on a
sharp rise in the duplicate ratio rather than on any duplication at all.

This is expensive on 500k rows. Run it daily at most, or on a sample.

## How to build it

Follow `scripts/collector_health_check.sh`, which already solves the plumbing:

- Script tracked in `scripts/`, deployed to `/home/orochford/bin/`. Keep the two in sync — they
  drifted once already (`7dd5d56c`).
- Resend key read from wileytest's `.env`; alerts to the address in `ALERT_TO`.
- Log to `/var/log/aunoo-embedding-health.log`.
- Repeat-alert suppression via `STATE_DIR`, 6 hours, cleared by a recovery.
- Root crontab. Every 30 minutes suits checks A–D; F, G and I belong on a daily run.
- **`TENANTS` must include every running tenant.** Since 2026-10-07 it lists all eight
  (bugfixing, wileytest, wiley, wbm, abm, oviva, panaya, sunstar). Add each new tenant there.

Reads can go through pgbouncer on 6432 as the collector check does. Anything doing DDL cannot —
wiley's pgbouncer runs `pool_mode = transaction`.

## Estimated effort (AI working time)

- Checks A–D, wired into a script in the existing style, with suppression and alerting: ~1.5h.
- Check F, including the state file and the trend logic: ~45m.
- Checks G and I: ~45m, once thresholds are chosen.
- Checks E and H: blocked on baselines. Measuring those is ~1h of query work, mostly waiting for
  a representative day of traffic.

## What this does not cover

Whether embeddings are *good*, only whether they exist. A drifting or misconfigured encoder that
produces valid 768-d vectors of poor quality passes every check here. The nearest available
signal is check I, and the closest thing to a real test is the re-encode comparison used on
2026-08-02: take a stored vector, re-encode the same article, and expect cosine 1.0. That is a
useful manual tool and could become a nightly sample-based check, but it is not specified here.
