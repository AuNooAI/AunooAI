# Runbook: 1536d → 768d article embeddings

How to move a tenant's `articles.embedding` from OpenAI's 1536-dimension vectors
to the local DeBERTa encoder's 768-dimension vectors, and how to get back if it
goes wrong.

## Where each tenant stands (checked 2026-08-19)

`emb_768_01` has already been applied everywhere. It cannot be rewritten — the
recorded history has to keep meaning what it meant when it ran. `emb_768_02` is
the forward repair for what it left unfinished.

| Tenant | alembic head | `articles.embedding` | 1536d backup table | HNSW index |
|---|---|---|---|---|
| bugfixing | `fa_012` | `vector(768)` | present, 51,526 rows | present |
| wiley | `fa_012` | `vector(768)` | present | present |
| wileytest | `fa_012` | `vector(768)` | **absent** | present |
| wbm | `bwr_001` | `vector(768)` | **absent** | present |

Rechecked on bugfixing on 7 October 2026: `articles.embedding` is still
`vector(768)` with `articles_embedding_hnsw_idx` (HNSW, `vector_cosine_ops`,
m 16, ef_construction 64), and `articles_embedding_1536_backup` still holds
51,526 rows. The alembic head on `test` is now `ip_001`, not `fa_012`. The
table above was not rechecked for the other tenants, and abm, oviva, panaya
and sunstar are not in it. All eight sites use the same encoder unit,
`deberta-encoder.service` on `127.0.0.1:8001`.

Where the backup is absent the original OpenAI vectors are gone, and a rollback
to 1536d is not possible from the database alone. `emb_768_01`'s downgrade now
refuses to run there rather than creating an empty `vector(1536)` column and
calling it a restore. Recovering those tenants means restoring
`articles_embedding_1536_backup` from a filesystem/database backup taken before
`emb_768_01` ran, then downgrading.

## Deploy sequence for a tenant not yet migrated

Run these in order. Every step is safe to re-run.

### 1. Preflight

```bash
cd /home/orochford/tenants/<tenant>.aunoo.ai
.venv/bin/python scripts/embedding_768_postbackfill.py --check
```

Reports the column width, how much of the table is populated, and whether the
index exists. On a pre-migration tenant it will report `vector(1536)` and stop —
that is expected, and it tells you the backup step still matters.

Confirm the encoder is up before going further; the backfill is useless without
it:

```bash
curl -s -X POST "${DEBERTA_ENCODER_URL:-http://localhost:8001}/encode" \
  -H 'Content-Type: application/json' \
  -d '{"title":"probe","description":"","content":"probe"}' | head -c 120
```

### 2. Back up the 1536d vectors

This is the step that makes the rollback real. Do it *before* the schema
migration; the migration drops the column.

```sql
CREATE TABLE articles_embedding_1536_backup AS
SELECT uri, embedding FROM articles WHERE embedding IS NOT NULL;

ALTER TABLE articles_embedding_1536_backup ADD PRIMARY KEY (uri);

-- Verify: this count must match, and must be non-zero.
SELECT
  (SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL) AS live,
  (SELECT COUNT(*) FROM articles_embedding_1536_backup WHERE embedding IS NOT NULL) AS backed_up;
```

Do not continue unless `live = backed_up`.

### 3. Schema migration

```bash
.venv/bin/alembic upgrade emb_768_01
```

This drops the 1536d column and the HNSW index, and adds `vector(768)` columns
on `articles`, `emerging_topics`, and `cluster_snapshots`. The two centroid
columns are derived data and are recomputed by the emerging-topics pipeline on
its next run; nothing needs restoring there.

Semantic search returns nothing between this step and the end of step 4. Run it
in a quiet window.

### 4. Backfill

The backfill does not run inside the app. `app/tasks/embedding_backfill.py`
defines a loop (`run_embedding_backfill`) and a one-shot function
(`backfill_embeddings`), but nothing in `app/` or `scripts/` calls either of
them (checked by code search on 7 October 2026). Someone has to run it by
hand, from the tenant directory, with the encoder up:

```bash
.venv/bin/python -c "import asyncio; from app.tasks.embedding_backfill import backfill_embeddings; print(asyncio.run(backfill_embeddings(limit=1000)))"
```

What it does (`app/tasks/embedding_backfill.py`):

- Picks rows `WHERE embedding IS NULL AND title <> ''`, 100 at a time,
  newest `submission_date` first. It does not filter on `ingest_status`, so
  it also embeds rejected, failed and social rows.
- Embeds the title plus the stored summary only. Ingest embeds the title, the
  tags and the page text (see "The encoder is down" below), so a backfilled
  vector is not the same as the one ingest would have written.
- Skips a row whose encode fails, leaving it NULL for the next run, and
  returns the number embedded. It stops after `limit` rows or when nothing is
  left.

Because of the first point, the backfill is a poor tool for repairing a few
approved rows on a tenant with many unembedded rejects. On bugfixing on
7 October 2026, 2 of 47,483 approved rows had no embedding, against 25,802
NULL rows in all (most of them `filtered_relevance` and `social_evaluated`),
so a `limit=1000` run would spend its whole budget on rejected rows first.

Watch progress:

```sql
SELECT COUNT(*) AS total, COUNT(embedding) AS populated,
       round(100.0 * COUNT(embedding) / NULLIF(COUNT(*), 0), 1) AS pct
FROM articles;
```

Expect hours, not minutes, on a large tenant. wileytest has ~683k articles.

### 5. Count verification and index build

```bash
.venv/bin/python scripts/embedding_768_postbackfill.py
```

This one command does the rest: it re-checks the column width, reports the
populated percentage, and builds `articles_embedding_hnsw_idx` with
`CREATE INDEX CONCURRENTLY` on an autocommit connection, so writes to `articles`
keep working while it builds. It then re-checks that the index exists and runs
`EXPLAIN` on a representative nearest-neighbour query to confirm the planner can
use it.

Run it again afterwards if you want; it is idempotent and will simply report
everything as already in place.

### 6. Record the repair revision

```bash
.venv/bin/alembic upgrade emb_768_02
```

`emb_768_02` verifies the same invariants and builds the index if step 5 was
skipped. Doing step 5 first is strongly preferred: the migration's build is a
plain `CREATE INDEX`, which holds a write lock on `articles` for its duration.

### 7. Backup retention

Keep `articles_embedding_1536_backup` for **90 days** after the migration. It is
the only rollback path. It costs roughly 6 KB per row (1536 float4s plus
overhead) — about 300 MB for 51k rows, 4 GB for 683k.

After 90 days, drop it deliberately, and record that the rollback path is gone:

```sql
DROP TABLE articles_embedding_1536_backup;
```

## Rollback

```bash
.venv/bin/alembic downgrade emb_768_01   # to just before it, i.e. kg_social_01
```

The downgrade:

1. refuses to run if `articles_embedding_1536_backup` is missing from the same
   schema as `articles`, naming what has to be restored first;
2. re-creates `articles.embedding` as `vector(1536)`;
3. copies every backed-up vector back;
4. counts what it restored and aborts if that does not match what the backup
   holds — a partial restore is reported, never accepted;
5. rebuilds the cosine HNSW index.

Centroids come back as empty `vector(1536)` columns on purpose: they are derived
from article embeddings and the pipeline recomputes them.

The round trip is covered by `tests/test_embedding_migration_roundtrip.py`, which
seeds fixture vectors in a disposable schema, downgrades, and compares the
restored vectors against the originals value by value.

## If something looks wrong afterwards

**Search returns nothing.** Check the populated count (step 4). A migration
followed by a stalled backfill leaves a valid, empty column.

**Search is slow but correct.** The index is missing. Run step 5.

**Inserts fail with a dimension error.** The column and the encoder disagree.
`scripts/embedding_768_postbackfill.py --check` says which width the column is;
the encoder writes 768.

**The encoder is down.** The encoder client never writes a placeholder
vector. `_encode_fields` in `app/vector_store_pgvector.py` raises on an
unreachable service, a non-2xx reply, a malformed reply or any width other
than 768, because a wrong vector in `articles.embedding` corrupts every later
search and cannot be told apart from a correct one afterwards.

What happens to the article depends on the path. This is the code at commit
`83fecd57`:

- **Live ingest.** After an approved save, `_process_single_article_async`
  calls `upsert_article_async` with a 30-second timeout
  (`app/services/automated_ingest_service.py:1456-1465`).
  `upsert_article_async` catches the encoder error itself and only logs
  "Async vector upsert failed" (`app/vector_store_pgvector.py:299-337`). The
  article stays approved with a NULL embedding. The batch still counts it in
  `vector_indexed` (`automated_ingest_service.py:1867-1869`), and nothing
  retries it.
- **Manual research.** `app/bulk_research.py:645-669` calls the sync
  `upsert_article`, which also catches and logs ("Vector upsert failed",
  `vector_store_pgvector.py:254-296`). Same result: the row stays NULL.
- **The backfill** (step 4) skips the row and leaves it NULL.

So after an outage, restarting the encoder is not enough. Once it answers,
find the approved rows it missed and embed them by hand:

```sql
SELECT count(*) FROM articles WHERE ingest_status = 'approved' AND embedding IS NULL;
```

Then run the backfill from step 4, keeping in mind that it also embeds
non-approved rows and uses title plus summary only. Automatic retry of
missing embeddings is not built yet; it is work package WP5b in
`docs/pipelines/08_INGEST_FIX_SPEC.md`.

The encoder unit itself has `Restart=always` (`systemctl show
deberta-encoder.service`), so a crash restarts it, but a hung process does
not.
