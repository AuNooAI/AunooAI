# Changes

Running log of notable operational/code changes. Newest first.

## 2026-08-02 — every monolith tenant moved to the local 768-d encoder (and a four-week wbm outage found on the way)

### Goal
None of this was planned. While fact-checking one line of `AI_DESIGN_PATTERNS.md` — the claim
that monolith retrieval embeddings are "OpenAI `text-embedding-3-small` (1536-d), silent
random-vector fallback" — the per-tenant check turned up a live failure on wbm. Fixing that
made the rest follow: bugfixing and wiley were the last tenants still embedding through OpenAI,
and leaving them there meant three different embedding spaces across four tenants.

### The wbm outage: four weeks with no embeddings at all
wbm's code embedded at 1536-d while its `articles.embedding` column was `vector(768)`. Every
upsert raised `expected 768 dimensions, not 1536`. The errors were arriving every few seconds
and had been since **2026-07-05**, so 26,348 articles were collected and none were vectorised.

The mismatch was somebody else's half-finished migration. wbm's `vector_store_pgvector.py` had
not been modified since 23 March and contains no 768-d code, so the 487,233 vectors already in
that database were never written by wbm's own application. The column and its data were
converted to 768-d on 5 July; the application was not.

**Why nobody noticed.** Brand alerts kept firing — 28, 17, 16 and 14 events in the weeks after
the break — because that path is SQL matching plus local classifiers and never touches
`articles.embedding`. What died was semantic: story clustering made its last assignment on 13
July, eight days after the break, which is how long the already-embedded backlog lasted. The
code says so plainly at `brand_watcher_stories.py:15` — "Articles without an embedding are
simply never written here." No error, no empty state, no warning. Stories stop growing and
searches return older articles that look plausible.

**Fix.** Copied wileytest's `vector_store_pgvector.py` onto wbm. The diff beforehand was 115
lines in exactly two hunks, both the encoder swap, with no wbm-local content elsewhere in 1,220
lines. Restarted, then backfilled the 26,348 stranded articles at ~36/s in 720s, zero failures.

### Proving the old vectors could stay
Before touching anything, the question was whether wbm's 487k existing vectors came from the
same encoder wileytest uses. If not, old and new vectors would sit in different spaces and
cosine distance across them would quietly return nonsense rather than erroring.

Re-encoded five sampled articles through wileytest's encoder and compared against their stored
vectors. **Three of five scored cosine 1.0000** on `title` + `summary`; the other two scored
0.91–0.93, consistent with summaries re-enriched after embedding. An exact 1.0000 cannot happen
across different models, so the corpus was already in the right space and no re-embed was needed
— only the 26k gap. The matching input convention is `{title, description: "", content: summary}`,
which is also what `embedding_backfill._doc_text` builds as `title\nsummary`.

### bugfixing and wiley migrated — `alembic emb_768_01`
New revision on each tenant, parented on their shared head `kg_social_01`. Canonical's chain
never carried wileytest's `emb_001`, so this is a new revision rather than a cherry-pick, with
identical DDL: `articles.embedding` plus the two derived centroid columns
(`emerging_topics`, `cluster_snapshots`) dropped and re-added at `vector(768)`, and the HNSW
index deliberately not recreated inside the migration — one bulk build after the backfill is far
cheaper than maintaining it across ~193k UPDATEs.

1536-d vectors cannot be cast to 768-d, so they are dropped rather than converted. Both tenants
got a `articles_embedding_1536_backup` table first (bugfixing 51,526 rows / 415 MB; wiley 80,982
/ 652 MB), which makes the migration's downgrade branch real rather than theoretical.

**Gotcha, wiley only — pgbouncer.** wiley's alembic resolves to `127.0.0.1:6432`, which is
pgbouncer running `pool_mode = transaction`, the mode that cannot carry this DDL. bugfixing
never hit it because its `.env` points at 5432. Ran the migration as
`DB_PORT=5432 DB_HOST=localhost .venv/bin/python -m alembic upgrade head`. **Check the port
before any future schema work on wiley.**

### Phase B (multilingual-e5, 1024-d) deliberately NOT ported
wileytest carries an `article_embeddings_ml` table with 520,249 E5 vectors, and the migration
plan treats it as part of the same work. It was skipped here after checking who reads it: within
the monolith, the only reference to `article_embeddings_ml` anywhere is `ml_embedding_task.py`,
which is the writer. No monolith service, route or task queries it. The actual consumers are all
on the saas side — `cascade_detect`, `cascade_directed`, `cascade_fingerprint`,
`cascade_retrieval`, `narratives`, `relevance/scorer`. Decision (user, 2026-08-02): if it isn't
used on wileytest, bugfixing doesn't need it.

### The backfill loops are not registered anywhere
`LOCAL_EMBEDDINGS_MIGRATION_PLAN.md` states both embedding loops were registered in the
`app_factory` lifespan with 60s/90s delays. They are not. Nothing imports `embedding_backfill` on
any tenant, neither loop is running on wileytest, and `app_factory.py` is byte-identical between
bugfixing and wileytest with no reference to either. **Backfill is operator-run in practice.**
New articles still embed inline through `upsert_article`, so the backlog does not creep back —
but a gap like wbm's will never self-heal.

### Verification
- **wbm, inline path — NOT yet verified end to end.** The backfill proves writes work, but new
  articles only reach `upsert_article` after the relevance and quality gates, and nothing has
  passed them since the 15:14 restart (`rss_feed_monitor`: `processed: 2, enriched: 2,
  relevant: 0, saved: 0, vector_indexed: 0`). 160 articles collected since the restart sit with
  `embedding IS NULL` as a result. That is the gate behaving normally, not a regression — but
  the live path stays unproven until an article qualifies. Re-check within a day.
- **wbm** — 26,348 embedded, 0 failed, 0 rows left NULL at the time of the backfill. `EXPLAIN` shows
  `Index Scan using articles_embedding_hnsw_idx`, and a probe vector from a 25 July article (i.e.
  inside the dead window) returns itself and sensible neighbours. Its index was already valid,
  1,943 MB over 513,581 rows; HNSW maintains on write, so backfilled rows folded in as written.
- **bugfixing** — 193,202 embedded in 9,573s (~20/s), 0 left NULL. HNSW rebuilt `CONCURRENTLY`
  in 342s, 740 MB, `indisvalid=t`, definition byte-identical to the pre-migration one
  (`m=16`, `ef_construction=64`). `EXPLAIN` confirms `Index Scan using articles_embedding_hnsw_idx`.
- **wiley** — complete. 265,062 articles embedded in 14,963s (~17.7/s), 100% coverage, 0 rows
  left NULL. HNSW rebuilt `CONCURRENTLY` in 469s, 1,026 MB, `indisvalid=t`, `indisready=t`.
  `EXPLAIN` confirms `Index Scan using articles_embedding_hnsw_idx`, and nearest neighbours for a
  probe vector are topically coherent (three fractional-SDE maths papers). Zero dimension errors
  since its restart. The build logged `hnsw graph no longer fits into maintenance_work_mem after
  16757 tuples` — a speed warning, not a correctness one; raising `maintenance_work_mem` would
  shorten future builds.
- Two concurrent backfills ran at 17/s and 21/s rather than halving each other, so the encoder
  service was not saturated by a single job.

**A verification that was wrong and had to be redone:** the bugfixing watcher's built-in
`EXPLAIN` check piped through `head -6` and showed only the subquery's `Seq Scan`, which reads
as "the index is not being used". The real plan is an `Index Scan`. Re-checked by hand with the
probe vector inlined. A truncated plan is worse than no check, because it looks like evidence.

### Ops — wbm added to the collector health check
`scripts/collector_health_check.sh` listed `TENANTS="bugfixing wileytest wiley"`. **wbm was never
in it**, so the one tenant nobody was watching is the one that then broke. The check would not
have caught *this* failure — it watches collection volume and the keyword-monitor heartbeat, both
healthy throughout — but wbm's absence meant it was uncovered for the failures it does catch: a
dead service, a hung collection loop, collection stopping outright.

Floor set to 20 articles per 12h from measurement, not a guess: wbm's 12h buckets over the 14 days
to 2026-08-02 have median 231 and p10 74, so 20 sits well under a normal weekend dip. Consistent
with wileytest at 30 and wiley at 10. Everything else is derived per tenant from the `.env` and the
systemd unit, which wbm already satisfies.

Verified by running the live script: `[wbm] OK: articles_12h=320`, no alert state files created.
Tracked copy and the deployed `/home/orochford/bin/` copy that root's `*/30` cron runs are
byte-identical again — they drifted once before (`7dd5d56c`).

A first measurement of wbm's volume showed 07-26 with 2 articles, which looked like an outage
worth alerting on. That was an artifact of a 7-day window cutting mid-day; the real figure is 322.
The floor would have been set wrong on it.

### Monitor built — `scripts/embedding_health_check.sh` (new) + INCIDENT (4 false alarms)
Checks A–D from the spec, in the same shape as `collector_health_check.sh`: Resend alerts,
6-hour repeat suppression cleared by a recovery, log at `/var/log/aunoo-embedding-health.log`,
state under `/var/tmp/embedding_health_state`. Root crontab at `15,45 * * * *`, offset from the
collector check at `:00/:30` so they do not hit the databases together. Covers all four tenants.

- **A** — the expected width is read from each tenant's own `EMBEDDING_DIM` (falling back to 1536
  if the file still names `text-embedding-3-small`) and compared against `articles.embedding`
  plus both centroid columns. This is the check that catches the wbm outage.
- **B** — probes `DEBERTA_ENCODER_URL/encode` and requires a vector of exactly that width.
  Skipped for any tenant still on the OpenAI path, which has no local encoder.
- **C** — counts `vector upsert failed|expected N dimensions|DeBERTa encoder unreachable` in the
  last 40 minutes of the journal.
- **D** — `articles_embedding_hnsw_idx` must exist and be `indisvalid`.

Deliberately absent: any "collected but not embedded" check. It fires on every quiet
relevance-gate spell — see the 160-article case in this entry's verification section, which
looked like a fault and was not.

**Verified by fault injection, not by assumption.** Each check was run against a sandboxed copy
(email disabled, own log and state dir) with a deliberate fault: code claiming 1024 against a
768 column, encoder URL pointed at a dead port, the journal pattern matched to live lines, and a
nonexistent index name. All four fired. The recovery path was tested too — the state file
appears on fault and is removed on the next clean run, logging `RECOVERED`.

**INCIDENT — the monitor's first live run sent 4 false alarms.** At 22:30 it emailed
`db_query_failed: Could not read index state (got: 'true')` for every tenant. Every index was
valid. `psql` renders `boolean::text` as `true` here, not `t`; the `case` matched only `t`, so
the healthy branch was unreachable and all four tenants fell through to the failure arm. It
would have fired every 30 minutes indefinitely.

Fixed by accepting both renderings (`t|true` / `f|false`), with a comment saying why. Stale
state files removed, and the deployed copy re-run to confirm: four `OK` lines, zero alert state
files, no Resend IDs in the log after 22:30:36. Checked the rest of the script for the same
fragility — `indisvalid` is the only boolean it compares.

**Lesson, and it is the point of the whole exercise:** the first version was run live against all
four tenants. The sandboxed copy that caught this class of bug in seconds was built minutes
later, for the fault-injection tests. Test a monitor in a sandbox first; letting it page you is
backwards, and a monitor that cries wolf on day one is the one people learn to ignore.

### Monitoring spec — `docs/EMBEDDING_HEALTH_MONITORING.md` (new, spec for A–I; A–D now built)
What to check so a repeat is caught in 30 minutes rather than four weeks. Checks A–D are
invariants with no baselines and no false positives: code-vs-column dimension, encoder reachable
at the right width, vector-write errors in the journal, HNSW index validity. **Check A alone
catches the wbm case.** Every query in the document was run against wbm before it was committed.
Checks E and H are specified but deliberately not implementable yet and say so — E needs the
gate-passed predicate pinned down or it fires whenever the relevance filter has a quiet spell,
and H needs an enrichment-cadence baseline.

### Propagation
All four monolith tenants now run the local DeBERTa 768-d encoder with no cloud fallback:
bugfixing, wileytest, wbm, wiley. **wiley was the last OpenAI embedding path on the platform**,
so no monolith tenant now sends article text to OpenAI for embedding — worth knowing for any
data-residency answer. Nothing was committed in wiley or wbm; both are deploy-copy trees.

Docs corrected to match, since several described the old world: `AI_DESIGN_PATTERNS.md` (§3.1
gotcha at 381, the 6.1 embeddings note at 810, Appendix B at 1083),
`ARCHITECTURE_SECURITY_MASTER.md` (§3.6 at 136–137, vector storage at 147, the third-party data
table at 254), and `METHODOLOGY.md` §2.6.

### Lessons
- **A column type is not proof the code agrees with it.** wbm's schema said 768 and its code said
  1536 for four weeks. Both bugfixing's "working" status and wbm's failure were initially inferred
  from code plus column type; only wbm's was checked against live write activity, and that
  inference is what hid the outage. Check that rows are actually landing.
- **Silent-skip is worse than a crash.** `bw_article_stories` skips articles with no embedding by
  design. That turned a hard write failure into an invisible four-week coverage hole, while the
  loud part of the system — alerts — kept working and made everything look fine.
- **Never assume alembic talks to postgres directly.** wiley routes through pgbouncer in
  transaction mode. Resolve the URL before running DDL.
- **A truncated `EXPLAIN` is misinformation.** Show the whole plan or don't claim the check ran.

## 2026-08-02 — session-doc tooling, and a technical reference for `/anticipate`

### Goal
Two separate pieces of documentation work on the same day.

First, this log had drifted: the newest entry was 2026-07-23 while commits ran through
2026-07-31 (`7dd5d56c`, 2026-07-31 22:56). The gap is a process problem, not a memory problem —
nothing prompted the write-up at the moment the work was fresh. Two artifacts to close it: a
skill that produces the documentation, and a hook that fires the reminder at commit time.

Second, the foresight stack behind the Anticipate tab had no code-level description anywhere.
`METHODOLOGY.md` covers it at the conceptual level and there were `how_it_works` pages for
Topics and the Forecast Tracker, but nothing wrote down the scoring formulas, the prompt
contracts, or which of the five subsystems share a pipeline. Writing that down also surfaced
four factual errors in the two existing pages.

### `session-docs` skill — `.claude/skills/session-docs/SKILL.md` (new)
A project-scoped skill, invoked as `/session-docs`. One evidence pass produces two deliverables:
this file's dated feature-by-feature entry, and a product write-up under `docs/product/`.

It defaults to **pre-commit mode**. Scope comes from `git diff HEAD` plus untracked files, not
from `git log`. There is no SHA yet in that mode, so the skill cites paths instead. It is told
never to invent one or leave a placeholder. Verification has to run *before* the commit: an entry
claiming verification that happens afterwards is a false claim.

The skill also carries this repo's own rules. Stage with `git add -u` plus an explicit add for
the new product doc, never `git add -A` — the 2026-07-23 secret-leak entry below is why. No
invented metrics. No `git checkout` of live UI-edited state. State propagation per tenant. Do not
fix code while documenting.

Two rules were added later the same day, after a dry run on the skill's own output. There is now
a third mode for work that cannot be committed at all, and the product doc must open with an
audience note when the work has no customer-facing surface. A plain-language rule was added after
that, on the same feedback.

### Pre-commit reminder — `.claude/settings.json` (new `hooks` block)
A `PreToolUse` hook on `Bash`. It reads the command with `python3` and exits silently unless the
command contains `git commit`. Then it checks whether `docs/changes.md` is staged or modified. If
it is, the hook says nothing. If it is not, it returns
`hookSpecificOutput.additionalContext` telling the model to run `/session-docs` first, with an
explicit escape hatch for trivial commits: typo, revert, WIP, docs-only.

It never blocks. It does not set `continue: false`, so a commit is never stopped.

Two details worth knowing. `jq` is **not installed** on this box; the first attempt used it and
failed, which is why the hook uses `python3`. And matching is a substring test on the raw command.
That is what makes `git commit -a`, `--amend`, and heredoc forms all match. The cost is that any
Bash command merely containing the text triggers the check.

`enabledPlugins` was preserved when the `hooks` block was merged in.

### `/anticipate` foresight reference — `docs/how_it_works_anticipate.md` (new) — `0dc0b00c`
1483 lines, written from source and cross-checked against live rows on wileytest. The framing
the page exists to record: **Consensus Analysis and Future Horizons are not separate pipelines**
— they are two of six *lenses* over one generation path (`GET /api/trend-convergence/{topic}`,
`trend_convergence_routes.py:564`), differing only in which articles get selected and which
prompt template is loaded. The tab is served at `/trend-convergence`; `/anticipate` is a nav
label and an nginx-side alias that appears in-repo only in outbound email links.

Documented end to end: the SHA-256 cache key and its `algorithm_version` bust lever
(`:2447-2487`); the corpus query; the per-lens weighting formulas quoted from
`weight_articles_for_dashboard()` (`:168-301`) — e.g. consensus scores `+5` for high
credibility and `+3` for the 30–180 day band, while horizons scores `+8` for `future_signal`
and only `+2` for recency; context-window-driven sample sizing (`:111-139`); the MD5-based
deterministic selector with its 60% category quota (`:1626-1700`); the four consistency modes
and their regex output-normalisation; prompt assembly from `data/prompts/*/current.json`; and
the shared output envelope. Then one section per subsystem, including the Forecast Tracker's
full A–F back-test with the aggregation formulas and verdict decision tree quoted from
`forecast_assessment_service.py:696-873`.

Two operational traps are called out because both are silent: `RERANK_ENABLED` defaults to
`"false"` (`reranker.py:42`), and with it unset every article falls into the ambiguous bucket
and every scenario returns Inconclusive; and `FORECAST_TRACKER_AUTO_RUN` is unset on most
tenants (`forecast_tracker_monitor.py:60`), so nothing re-assesses automatically and an amber
health dot means nobody pressed Reassess rather than a fault.

### Drift corrections in two existing pages — `0dc0b00c`
Writing the reference meant checking the older pages against code. Six errors in
**`docs/how_it_works_forecast_tracker.md`**, four of which would mislead someone debugging:

- Classifier default given as `gpt-4.1-mini`. That is the prompt template's advisory
  `model_recommendations` field; the runtime default is
  `DEFAULT_CLASSIFY_MODEL = "gpt-5.4-mini"` (`forecast_assessment_service.py:44`).
- Strengthening / Stable / Cooling presented as verdict labels. They are the customer-facing
  rendering of the *baseline-correction* axis (`forecast_narrative.py:34-38`); the verdicts are
  Accelerating / On-track / Stalled / Off-track / Inconclusive / Done. The page now documents
  both axes and why the header chip can read "Strengthening" while the card reads "On-track".
- A "fallback to corpus-wide retrieval if the topic is too narrow" that does not exist —
  `_fetch_window_articles()` (`:470-533`) is a single query with no widening branch. The actual
  mechanism is `source_topics`. Also corrected: the window cuts on `submission_date`, not
  `publication_date`, and `embedding IS NOT NULL` is a hard filter.
- Classifier described as returning three values; the enum has six, plus an evidence type and a
  confidence score, with a 0.5 confidence floor before anything counts.
- Surprise residual described as the ambiguous bucket only; it is ambiguous ∪ `unrelated`, with
  an 8-article floor below which the panel is skipped.
- "Re-runs overwrite the most recent assessment" — `save_forecast_assessment` is a plain
  `INSERT` (`database_query_facade.py:8011`). Nothing is overwritten; the tracker reads the
  latest row, which is what the trajectory heatmap is built from.

**`docs/how_it_works_topics.md`** carried the same corpus-wide-fallback and three-verdict errors
in §6.2, plus two stale model names: the theme proposer is `gpt-5.4`
(`theme_proposer.py:97`, now cited as the config attribute so a repoint does not re-stale the
doc) and the promotion-path Three Horizons call is `gpt-5.4`
(`wiley_candidate_pipeline.py:637`), both previously documented as `gpt-4o`.

Checked and deliberately left alone because they are correct: the relevance judge
(`gpt-4.1-mini`, temp 0.2, 600 tokens, matching `wiley_relevance_judge.md`) and the overlay
agent (`gpt-4.1` from the agent frontmatter plus `reasoning_effort='high'` injected by the
caller at `wiley_overlay_generator.py:193`).

### Verification — `/anticipate` reference
Documentation has no test suite; verification here means every non-obvious claim was re-checked
against code or live data before the commit, and again while writing this entry.

- Code facts re-grepped: `DEFAULT_CLASSIFY_MODEL = "gpt-5.4-mini"` (`:44`);
  `RERANK_ENABLED` default `"false"` (`reranker.py:42`); `FORECAST_TRACKER_AUTO_RUN` gate
  (`forecast_tracker_monitor.py:60`); `insert(t_forecast_assessments)` (`:8011`);
  `default_model: str = "gpt-5.4"` (`theme_proposer.py:97`); `get_ai_model("gpt-5.4")`
  (`wiley_candidate_pipeline.py:637`). `_fetch_window_articles()` re-read in full — no fallback
  branch present.
- Live data on wileytest (79 consensus runs, 80 horizons runs, 32 assessments): verdict labels
  in use are Inconclusive 102, On-track 15, Accelerating 6, Stalled 3 — confirming the label set
  and that Off-track and Done occur zero times in current data. Article verdicts across 573
  rows: `supports_trajectory` 251, `neutral_context` 126, `better_fits_other_scenario` 116,
  `unrelated` 48, `supports_state_contradicts_trajectory` 27, `contradicts` 3.
- Assessment `config` read from the newest row confirms the documented tunables:
  `{max_articles: 2000, stage_a_top_k: 150, stage_b_min_score: 0.5, stage_c_margin: 0.04,
  window_weeks: 8}`.
- Scenario-type distribution across `future_horizons_runs`: h1 368, h2 364, h3 251, plus
  probable/plausible/possible/preferable from the Futures Cone prompt — which is what confirmed
  two scenario vocabularies coexist in the same table.
- **Found while verifying, not fixed:** 2 of 573 `forecast_article_verdicts` rows carry an
  *evidence type* in the `verdict` column (`anecdote` 1, `leading_indicator` 1). The classifier
  parser accepts whatever string the LLM returns for `verdict` without validating it against the
  six-value enum. Low impact — `_aggregate_scenario()` counts by exact match, so these rows fall
  through every bucket and land in `neutral` — but it means a malformed response is silently
  miscounted rather than retried. Not touched, per documentation-only scope.
- **Not verified:** the `raw_output` double-encoding gotcha and the deck-overlay
  match-by-`topic`-field behaviour are documented from reading the code paths
  (`forecast_assessment_service.py:102-104`, `:1140-1155`), not from an executed test.

### Verification — hook and skill
- Hook, three cases piped as synthetic stdin: `git commit` with `docs/changes.md` untouched →
  emits the JSON; non-commit command (`ls -la`, `pytest -q`) → silent, exit 0; `git commit`
  with `docs/changes.md` modified → silent, exit 0.
- Round-trip: command re-extracted *from* `.claude/settings.json` and re-run — escaping
  survived, output parsed as valid JSON (459-char `additionalContext`), plugins intact.
- Hook proved live: it fired on a real Bash call in-session (that call's command text contained
  `git commit`) and the reminder arrived as a system-reminder.
- Skill proved discoverable: `/session-docs` loaded and this entry was written by following it.
- **Not verified**: behaviour on a genuine `git commit` — no commit was made this session.

### Propagation — docs
Committed to canonical (bugfixing) as `0dc0b00c` on branch `fix/enrichment-retry-empty` — note
that is a code branch, not a docs branch, so the three pages do not reach `main` until it
merges. Docs-only: no service restart, no UI rebuild, no tenant copy needed. The pages describe
canonical behaviour and are accurate for wiley / wileytest as long as those trees are not
drifted on the files cited; per-tenant `.env` differences (`RERANK_ENABLED`,
`FORECAST_TRACKER_AUTO_RUN`) are called out in the text rather than assumed.

The same commit also carried `docs/changes.md` backfill entries and the two `docs/product/`
writeups that an earlier session had left uncommitted — included because `changes.md`'s newest
entry references the product docs, so committing one without the other would leave a dangling
reference.

### Propagation — hook and skill: none, and it cannot propagate
`.gitignore:49` ignores `.claude/`, so **both files are untracked and uncommittable in this
repo**. They are local to this checkout only: not committed here, not carried to wiley /
wileytest / wbm / saasmvp-app, and not inherited by a tenant cloned from canonical. Any tenant
that wants them needs the two files copied in by hand. This entry is therefore the only
durable record that they exist.

### Lessons
- Don't assume `jq` — it is absent on this host, and every hook example in the wild uses it.
  `python3` is present and does the same job.
- A hook that nags unconditionally gets ignored. Gating the reminder on "is `docs/changes.md`
  actually absent from this commit" is what keeps it credible.
- **Never read a model name out of a prompt template or agent frontmatter and document it as
  what runs.** `data/prompts/*/current.json` carries `metadata.model`, and
  `forecast_assessment/current.json` carries `model_recommendations`; both are advisory. This
  was the single largest source of stale model names across the `how_it_works` pages — three of
  the six corrections traced to it. Cite the service constant or the `get_ai_model()` call site.
- When a doc says a pipeline has a fallback, check for the branch before repeating it. The
  "corpus-wide fallback" claim had propagated into two pages and describes code that has never
  existed; it makes an empty-pool assessment look like a retrieval bug rather than a missing
  `source_topics` mapping.

## 2026-07-31 — observer alerts mislabelled news as social; two ops monitors

Backfilled 2026-08-02. Detail below is from the commit messages except the propagation table,
which was measured on 2026-08-02.

### Observer alerts: news articles labelled "Social" — `00cb9683`
`social_ref()` had a catch-all branch. Anything that was not Bluesky, X, or Reddit came out as
`source · Social · view post`. Most observer matches are news URLs (nature.com, cnn.com,
arxiv.org), so most matches were labelled wrong, in both the alert email and the online report.

Non-social URLs now show their publisher domain, the word "News", and "read article", and link
to the site. Instagram and TikTok post URLs (xpoz platforms) are now recognised as social.
**`app/routes/vector_routes.py`**, **`app/services/email_service.py`**.

### Ops — saas email-delivery check — `9357f4f3`
A one-shot check on the three saas changes that shipped 2026-07-31, queued with `at` for 21:00
on 08-01. Each area gets its own verdict, so a green area cannot hide a red one in the subject
line. The three areas:

- **Correspondent email.** The Newsroom-tier gate came off and 19 agents were backfilled. The
  real signal is matched runs that produced *no* email.
- **Editor advisory-lock timeouts.** Reported as failures over ticks, with the 8.7% baseline
  printed next to it. A raw count means nothing without knowing how often the lock was tried.
- **Editorial `fabricated_claim` rejections**, against a baseline of 356 in 30 days.

The lock and editorial windows start at the 22:03 deploy rather than a rolling 24 hours, so
pre-fix hours do not dilute the numbers. The script reads the journal for both `saas-worker` and
`saas-skills-worker`. Two dry runs found psql column headers leaking into scalar values, which
had also broken the empty-result fallbacks.

**`scripts/saas_email_delivery_check.sh`**, deployed to `/home/orochford/bin/`, logging to
`/var/log/aunoo-saas-email-check.log`. It does not reschedule itself.

### Ops — collector health check, tracked copy resynced — `7dd5d56c`
The tracked copy had drifted from `/home/orochford/bin/collector_health_check.sh`, which is what
root's `*/30` cron actually runs. Version control did not hold what was live.

The gap was one comment line, recording that abbott left `TENANTS` when it shut down on 07-16.
Behaviour is the same either way. The sync went tracked ← live: live is what runs, and it held
the extra context.

### Propagation (measured 2026-08-02, md5 vs canonical)
`vector_routes.py` and `email_service.py` are identical on wiley and wileytest — the observer
labelling fix is on both.

## 2026-07-30 — post-Bedrock breakage sweep (11 fixes)

Backfilled 2026-08-02. Eleven fixes with one root cause. The Bedrock migration moved every tenant
off OpenAI. Code that still expected an OpenAI model, OpenAI-shaped JSON, or a `python` on PATH
then broke, and broke quietly. Detail is from the commit messages. Propagation was measured on
2026-08-02.

### Enrichment: retry on empty or unparseable response — `c6bb7a84`
Reasoning models on Bedrock (Kimi, Nova) sometimes return text the Key:Value field parser cannot
read. The commit message puts it at roughly 1 in 8. One miss was enough to mark the article
`enrichment_failed` (`Available fields: []`).

`generate_response` plus the parse now run inside a 3-attempt retry, so a bad response recovers
instead of failing the article. **`app/analyzers/article_analyzer.py`**.

### Event-loop watchdog was crashing the process — `7258071e`
The watchdog armed `faulthandler.dump_traceback_later(all_threads)` on every cycle. When the loop
blocked for more than 8 seconds, that walked every thread's `PyThreadState` from a timer thread.
It raced native-extension code and thread teardown, and segfaulted inside
`_Py_DumpTracebackThreads` (crash IP `0x4bb854`, `segfault at 0x70`). It took wileytest down twice
on 2026-07-30, during enrichment and hybrid relevance.

The C-level watchdog now sits behind `EVENT_LOOP_WATCHDOG=1` and is **off by default**. Diagnosis
survives without it: the async lag WARNING, the ring buffer, and the admin endpoint's GIL-safe
`dump_all_thread_stacks()`. **`app/utils/event_loop_monitor.py`**.

### Add-Topic wizard: keyword suggestion dead on Bedrock — `3f6302c2`
`/api/onboarding/suggest-topic-attributes` looked through `litellm_config` for the first
`openai/` model with an API key. After the Bedrock migration there is never one, so it raised
"No OpenAI model configured" and the wizard quietly stopped calling the LLM at all.

It now resolves a bare alias through `resolve_litellm_call_params`, and defaults to a Claude
alias because Nova's structured JSON is unreliable. **`app/routes/onboarding_routes.py`**.

### Foresight model dropdown: real models, not aliases — `1ddef137`
`litellm_config` exposes about two dozen aliases (`gpt-*`, `gemini-*`, `mixtral-*`,
`claude-*-latest`). They all collapse onto a few real models: Claude Sonnet 4.5, Claude Haiku 4.5,
Nova Pro, Nova Lite, Kimi.

The `/models` endpoint returned all of them. That mislabelled Claude as GPT and Gemini, showed
duplicates, and included a fallback that gave id `gpt-5.4` the labels "GPT-4.1" and "GPT-4o". It
now returns the 5 distinct models under honest names.
**`app/routes/trend_convergence_routes.py`**.

### Trend convergence: org profile never loaded, and JSON parsing was brittle — `f27e8bb8`
Two problems in one route.

`get_organisational_profile` returns a SQLAlchemy mapping keyed by column name. The route read it
positionally as `profile_row[0]`, which raised "Could not locate column in row for column '0'".
The profile silently never loaded. It is now read by name, and tolerates a value that arrives as
JSON text or as already-decoded JSONB.

The AI-response JSON extraction used a non-greedy regex and a first-`{`-to-last-`}` scan. Nested
objects or trailing prose returned a 500. It now goes through the shared `_preprocess_response`
and `json.raw_decode`, and only 500s when nothing parseable is left. The outer `except` also
stopped re-wrapping the `HTTPException`. **`app/routes/trend_convergence_routes.py`**,
**`requirements.txt`**.

### Collectors — `4bd1aa45`, `1c09aebf`
**NewsFirehose.** Publisher and keyword names containing `&`, such as "John Wiley & Sons" and
"Taylor & Francis", reached the `/v1/search` tsquery builder and raised `PostgresSyntaxError`
(500). `_normalize_query` now strips literal tsquery operators (`& ! : * \`), so those terms
degrade to plain words.

**TheNewsAPI.** `keyword_monitor` passes `search_fields` as a comma-separated string. Calling
`",".join()` on a string iterates its characters, which produced
`search_fields=t,i,t,l,e,,,d,…`. A string is now split into a list first, which is what
`newsapi_collector` already did.

### Ingest and services — `0bbbc7db`, `28fe09d2`, `0ab6a203`, `9876623c`
Four small failures, each of which stopped work silently.

- **Hybrid relevance scoring.** `article_data` can carry a content or summary key whose value is
  an explicit `None`, so `.get(k, '')` still returned `None` and `len()` raised. Now coerced with
  `or ''`.
- **Firecrawl batch scrape.** An empty or all-invalid URL list made the call 400 with "No valid
  URLs provided". The call is now skipped.
- **Data-quality check.** It parsed the LLM reply with `json.loads`, which throws "Extra data"
  when the model adds prose after the object. It now starts at the first `{` and uses
  `raw_decode`.
- **Brand-watcher auto-retrain.** It shelled out to `python`, which does not exist on these hosts
  — only `python3` and the venv — so it failed with Errno 2. Now uses `sys.executable`.
- **Analysis cache.** Long URLs, such as Google News RSS article IDs, produced filenames over the
  255-character limit (Errno 36, silent cache-write failures). The URL portion is now capped with
  a SHA1 of the full URL appended. Short URLs keep their old names, so no existing cache entry is
  invalidated.

### Briefing Desk: model pinned server-side — `e79b7aa3`
The daily briefing's draft, incident detection, and final synthesis now read the model from
`emerging_topics_settings.model`, which overrides the browser dropdown. Composed content and the
`model_used` byline are therefore the same for everyone on a tenant. If the setting is unset, it
falls back to the model the client passed. **`app/routes/daily_reports_routes.py`**,
**`app/services/daily_briefing_compose_service.py`**.

### Propagation (measured 2026-08-02, md5 plus marker grep against canonical)
Every file is identical on wileytest. On wiley, every file is identical except two.

**`trend_convergence_routes.py` — wiley was missing `1ddef137`.** Fixed on 2026-08-02, see below.
It still carried the old alias list: 2 hits of the `'GPT-4.1'` label, where canonical and
wileytest have 0, and 3869 lines against 3831. It did have `f27e8bb8`, both the by-name
`profile_row['id']` access and the `raw_decode` path. That dates wiley's copy to between 16:05
and 16:24 on 07-30 — taken 18 minutes before the dropdown fix landed. Wiley showed fictitious
GPT and Gemini entries in its foresight dropdown for three days.

The fix, 2026-08-02. `diff -u` against canonical showed exactly one hunk, confined to the
`/api/trend-convergence/models` endpoint. There was no wiley-local divergence anywhere else in
the file, so copying the whole file was safe and a surgical hunk apply was unnecessary. Steps:
backed up wiley's copy off-tree, copied canonical over it (both now md5 `30b0c46e`), ran
`py_compile` under wiley's own venv, restarted `wiley.aunoo.ai.service` (active 10:38:53 CEST).
Verified against the running service: `curl http://127.0.0.1:10006/api/trend-convergence/models`
returns the 5 real models, and the `'GPT-4.1'` label count is 0. Nothing was committed in wiley,
which is a deploy-copy tree.

**`automated_ingest_service.py` differs by 61 lines, but has the fix.** The `0bbbc7db` `or ''`
guard is present at line 447. That diff is unrelated tenant drift.

One thing flagged but not changed, and not a propagation gap: a positional `profile_row[0]`
survives in this file on all three tenants, canonical included. It is a different code path that
`f27e8bb8` did not touch.

## 2026-07-30 — EU AI Act Article 50: label AI-generated output — `25812e69`

Backfilled 2026-08-02.

`app/compliance/ai_disclosure.py` is now the single source for two things: the visible
"AI-generated" disclosure, and the machine-readable marker. One source means they cannot drift
apart between output formats.

It is wired into email (an opt-in `X-AI-Generated` header plus a footer), HTML, PPTX, DOCX and PDF
reports, dashboard exports, and the in-app React dashboards. UI copy that claimed more than we do
— "reviewed and validated" — was softened at the same time. The commit touches 18 service files
plus the React build and templates.

### Propagation
`ai_disclosure.py` identical on wiley and wileytest (measured 2026-08-02). Per
`project_euaiact_art50_compliance`, this also shipped to the saas side (canonical `saasmvp-app`,
commit `4ef4930`) — not re-verified here.

## 2026-07-29 — enrichment loss: parser, prompt, and the relevance gate

Backfilled 2026-08-02. The highest-impact day in this range. News articles were enriched, then
silently discarded, then made permanently invisible. The measurements below come from the commit
messages. Propagation was measured on 2026-08-02.

### Root cause: the parser threw away whole analyses over heading wording — `b266238c`
`parse_analysis()` checked the model's response by exact heading match across 14 required fields.
Several ordinary things broke that check:

- the model renamed a heading, for example "Driver Signal Explanation"
- it numbered the headings, "1. Category", which the prompt's own numbered list invited
- it wrapped them in markdown
- it merged the four rationales into one "Explanation" block
- it left out "Title"

Any one of those threw the **entire analysis** away, and the row kept a NULL `category` and
`sentiment`.

That is worse than it sounds. Every observer agent retrieves on
`sentiment IS NOT NULL AND category IS NOT NULL` (`vector_routes.py`). So the article vanished
from signal alerts, `/explore`, and reports — permanently, because nothing retries it. On
wileytest this hit about 227 news articles a day. Social posts enrich on a different path and
were fine, which is why agent output had drifted toward Bluesky.

The parser now:

- strips list markers and markdown from headings **and** values. A leading `**` on a value used
  to reach the ontology check as `** Widespread adoption` and get downgraded to "Other".
- maps known heading variants onto the canonical names
- reuses a merged "Explanation" block for the per-field rationales
- falls back to the caller's title when "Title" is missing
- hard-fails only on Title, Summary, Category and Sentiment. Descriptive fields now warn and
  store blank instead of voiding the whole record.

`scripts/reenrich_parse_failures.py` recovers the backlog. It checks each topic's ontology first
and skips any topic with an empty list, because `analyze_content()` rejects those before it ever
calls the model. Wileytest's "M&A Updates" has no `future_signals`, which blocks 3,003 articles.
That is a config problem, not a parsing one.

The commit also isolates `PromptManager` storage in tests.
`PromptTemplates.load_custom_templates()` calls `save_version()`, so running the suite had been
overwriting the live `data/prompts/current.json` with the test fixture's placeholder prompt.

### The prompt was inviting the drift — `8712c41c`, then `3f37ef27`
Six defects in the analysis prompt. Each one maps to a failure in the logs:

- Two competing "Format your response as follows:" blocks. The first listed only "Summary:", so
  a model that anchored on it emitted nothing else.
- Sections numbered 1–8, which came back as headings.
- Section 8 titled "Relevant tags" against a "Tags:" output label. Two names for one field.
- "Title" never requested in the instructions at all. This was the largest single missing field.
- "Provide a brief explanation" without naming the target field, which invited one merged block
  instead of four labelled ones.
- "regarding the future of AI" on every topic, including M&A Updates and Geopolitical Hotspots.

The replacement uses unnumbered sections keyed to the exact field labels, one output block, and
an explicit instruction against numbering, markdown, and renaming.

Measured A/B on the same 12 articles with `bedrock-kimi-k2.5`: the old prompt produced 10 clean
and 2 drifted, and both drifts were the exact failure modes dominating the production logs. The
new prompt produced 12 clean, 0 drifted.

Written with `PromptManager.save_version` (v1.0.3 → v1.0.4) on bugfixing, wileytest and wiley.
All three report template hash `ec7112190aee`. `get_template_hash` feeds the analysis cache key,
so analyses cached under the old prompt invalidate themselves.

`3f37ef27` then fixed the hardcoded default. `8712c41c` had rewritten
`data/prompts/content_analysis/current.json`, which is what existing tenants run, but
`PromptTemplates.DEFAULT_TEMPLATES` still carried every defect that rewrite removed.
`initialize_defaults()` only seeds when no stored version exists, so this changes nothing for an
existing tenant. It matters for a **newly cloned** one, which would otherwise start life with the
exact prompt that was causing analyses to be discarded — the bug reappearing silently, months
later, on a fresh deployment.

### Relevance gate: the CE tier was one flag away from an outage — `128d037a`, `540584d4`
`RELEVANCE_USE_CE_TIER` is off by default, and that default was the only thing preventing a
serious outage.

Measured against a 49-item hand-labelled gold set on wileytest, 20 genuinely relevant and 29 name
collisions:

| | min | median | max |
|---|---|---|---|
| relevant | 0.000018 | 0.0029 | 0.80 |
| collisions | 0.000016 | 0.000018 | 0.0049 |

The shipped `CE_LOW=0.10` sits above 90% of the *relevant* population. Turning the flag on would
have "confidently rejected" 18 of the 20 relevant articles, with no LLM review at all.

There is no honest reject threshold here. The widest cut that loses no positive is 0.000018, and
that is the lowest positive. A coincidence, not a margin.

So the tier is accept-only now. The risk is asymmetric: a wrong confident accept costs one
enrichment call, while a wrong confident reject drops the article for good. That is the same
failure mode that made news disappear from the observer agents. `CE_HIGH` dropped from 0.90 to
0.05, an order of magnitude above the worst collision — 0.0049, "Sage Group (OTCMKTS:SGPYY)", the
accounting software firm, not SAGE Publishing. On accept, the hybrid score is raised to the
threshold rather than overwritten with the CE value, whose scale is not comparable to the
embedding and classifier scale.

`540584d4` then corrected its own predecessor's measurement. `128d037a` justified the tier with
"AUC 0.907, better than any reworded query". That number scored **titles only**, while
`_compute_cross_encoder_score` builds `f"{title}. {summary}"`. Four of its 20 positives were
hand-written titles rather than real rows.

Re-measured on real articles, with real summaries, in the production document form:

- **theme topics, AUC 0.885** — 199 relevant, 114 not, weak-labelled from the pipeline's own
  confident extremes
- **brand topics, AUC 0.478** — 9 relevant, 86 not, hand-labelled. That is a coin toss.

Rewording the query does not rescue the brand case: bare entity 0.298, "news about X" 0.425,
question form 0.402, "X the company" 0.609, raw topic 0.478. The reason is that brand topics need
entity disambiguation — SAGE Publishing, Sage Group plc, sage the herb, and sage-agent-sdk on
PyPI. That is a named-entity problem, and a semantic reranker rates all four alike.

So the tier is theme-topics-only now. The flag still defaults off. This makes it safe to turn on;
it does not turn it on.

One thing `540584d4` flagged and left open. The gate uses its own brand predicate, because the
existing `is_brand_topic` only matches "Brand Monitoring X" and misses the live "X - Brand Watch"
topics (78 articles, most recent 2026-07-27). The narrower predicate was left alone rather than
silently changing which topics the classifier-confidence guard covers.

### Propagation (measured 2026-08-02)
`article_analyzer.py`, `prompt_templates.py` and `hybrid_relevance_service.py` are identical on
wiley and wileytest.

## 2026-07-23 — prod tenants under version control + INCIDENT (secret leak / file deletion)

### Goal
Get a restorable copy of the prod tenants into git. wileytest IS prod (despite the name);
wbm is prod. bugfixing is dev/canonical.

### What was done
- **wbm** — was not a git repo at all; `git init` (local, branch `master`, no remote). Hardened
  its `.gitignore` first; verified no secrets tracked.
- **wileytest** — pushed a **clean restore-point snapshot** to a dedicated private repo
  `AuNooAI/wileytest-prod` (branch `main`). Method: build a single orphan commit from the
  working tree in a THROWAWAY index (`GIT_INDEX_FILE=$(mktemp)` + `git add -A` + `commit-tree`),
  strip `.github/workflows/*` (so a `repo`-scoped token suffices, no `workflow` scope), and
  push that commit ref directly. This never switches branches on the live checkout and never
  drags git history — so the snapshot is ~43 MB, not the 980 MB (wileytest) / 19 GB (bugfixing)
  of legacy chromadb/sqlite blobs still in both repos' shared monolith history.

### Why the naive approaches don't work (for future reference)
- Pushing a branch (`training:main`) drags full history = ~980 MB of legacy `chromadb/chroma.sqlite3`
  (73 MB) + `fnaapp.db` (52–66 MB) blobs. `.gitignore` excludes these in the *working tree* but
  NOT in history. Only a history-free orphan snapshot (or a `filter-repo` purge) avoids it.
- Prod tenants are **deploy-copy targets**: files are rsync'd/copied in and never committed, so
  the working tree has UNTRACKED `.py` (19 on wileytest), `.env` backups, and a legacy `chromadb/`
  dir that git doesn't track. Dev (bugfixing) commits everything → 0 untracked app files.

### INCIDENT (my error) + recovery
While building the snapshot on the LIVE checkout with `git checkout --orphan … && git add -A &&
git checkout training`, two things went wrong:
1. **Deleted ~18 untracked deploy-copied files from prod's disk** — the branch-switch back to
   `training` removed files that `git add -A` had tracked in the orphan branch but `training`
   didn't. Prod stayed up (running from memory) but was one restart from breaking. **Recovered**
   by restoring the working tree from the snapshot commit (`git checkout <snap> -- .`).
2. **Pushed 47 live secrets** — `git add -A` swept in untracked `.env.pre_bedrock_*` (real keys:
   OPENAI/ANTHROPIC/AWS_BEDROCK/DB_PASSWORD/RESEND/FLASK_SECRET/…) that wileytest's `.gitignore`
   didn't cover, into a snapshot pushed to the (private) `wileytest-prod`. **Contained** by
   deleting+recreating the repo; owner rotated the exposed keys.

### Fix — hardened `wileytest/.gitignore`
Added broad exclusions so `git add -A` can never sweep these again: `.env.*` (keep
`*.example`/`*.template`), `**/.env.hub`, `*.pre_bedrock*`, `*.key`, `*.pem`, `bedrock.key`,
`opointkeys`, `*.bak_*`, `config.json.bak*`. Verified with `git check-ignore` (patterns hit) +
a mandatory pre-push secret scan on the built commit tree (`git ls-tree | grep -i secrets` →
must be empty, else abort). The safe orphan-snapshot method now bakes this scan in as a gate.

### Lessons
- NEVER `git checkout --orphan` / branch-switch on a live deploy-copy checkout (untracked files
  get deleted). Build snapshots via a temp `GIT_INDEX_FILE` + `commit-tree` instead.
- NEVER `git add -A` on prod without a hardened `.gitignore` AND a secret scan of the resulting
  tree BEFORE pushing.

## 2026-07-23 — back-port prod-only fixes into canonical (drift audit: PROD ahead)

A drift audit of bugfixing (canonical) vs wileytest (active prod) found several fixes that
were made in place on prod's `training` branch and never flowed back to canonical — so any
tenant cloned from canonical would be stale. Back-ported the three that matter:

- **`automated_ingest_service.py`** — unknown-topic guard (prod commit `6229dc9f`). If an
  article's topic isn't in the loaded config, mark it `skipped_unknown_topic` and make ZERO
  LLM calls, instead of never marking it done and re-selecting it forever (~5 LLM calls/pass).
  This loop is what drained the OpenAI account on 2026-06-18. Canonical (and clones) lacked it.
- **`geopolitical_service.py`** — bulk `GROUP BY … FILTER` aggregation (prod `9ee94a21` +
  `7d24219d`) replacing a per-hotspot loop that ran a full-table ILIKE seq-scan per unlinked
  hotspot (~6.7k scans/run); also drops the now-dead `sentiment_to_score` helper.
- **`geopolitical_hotspots_monitor.py`** — wrap `update_country_stats` / `update_hotspot_trends`
  in `asyncio.to_thread` on the `run_schedule` path (prod extended `9203117b`) so the scheduled
  stats run doesn't block the event loop.

Each was a confined change (verified: only diffs were the intended fix, no unrelated prod-local
content), so canonical adopted prod's version of the file wholesale. py_compile clean.

NOT touched: `vector_store_pgvector.py` (intentional per-tenant DeBERTa-768d vs OpenAI-1536d
split — schema-bound), `training_routes.py` (ce_score tied to the `ce_001` migration prod lacks),
`server_run.py`/CORS, `database_query_facade.py` (prod-local xpoz `social_meta`), the xpoz
collector registration, and the Threat-Intelligence module — all intentional divergence.

## 2026-07-23 — signal reports: inline account/post links + complete online report

### Ask
The alert email/report should link accounts and posts inline (click an @handle → the
profile, a post → the post), and the online "View full report" page was incomplete —
it showed only the narrative, not the matched source posts the email lists.

### Fix — `app/services/email_service.py` + `app/routes/vector_routes.py`
New shared helpers in `email_service.py`:
- `social_ref(uri)` → `{short, profile, post, platform}` parsed from a bsky/x/reddit post URL.
- `linkify_handles_md(md, matches)` → turns plain `@handle` in the report markdown into
  `[@handle](profile_url)` using the matched posts' URLs (deterministic — no LLM/hallucination).
- `render_matched_sources_html(matches)` → clean linked source cards (account link · platform ·
  view-post link · summary · threat/confidence).

Wired into both channels so they match:
- **Email** (`send_signal_alert_email`): linkify the narrative before render; the old
  raw-URL "Matched Articles" list replaced by `render_matched_sources_html` ("Matched posts").
- **Online report** (`/signal-reports/{id}/download`): now also SELECTs `alerts_data`, linkifies
  the narrative, and appends a **Sources** section (same cards) — so the loadable report is as
  complete as the email. Render-time, so already-saved reports gain it on next open.

Handles remain shortened (`@name`) as anchor text; no bare URLs in prose (strip still runs).

### Verification
Online report 647: 25 `@handle→profile` links in the narrative, Sources section with all 7
matched posts + "view post" links, 0 raw bare URLs, heading renders. Email sent through the new
path. Applied + py_compile + restart on all 4 tenants.

## 2026-07-23 — reports: render leading-space markdown headers (raw "# Title" in loadable report)

### Symptom
A signal report opened via the emailed "View full report" link (and the email's own
report section) showed a literal `# Negative Social Narrative Summary: Wiley…` instead of
a rendered heading, while `## Sub-headings` rendered fine.

### Root cause
`markdown_to_html` (shared by the email report section and the `/signal-reports/{id}/download`
HTML view) uses python-markdown, which renders an ATX header indented by **1–3 spaces** as a
paragraph, not a heading. The LLM emitted the top heading as `" # Title"` (one leading space),
so only that first heading failed.

### Fix — `app/services/email_service.py`
De-indent ATX headers before rendering: `re.sub(r'(?m)^[ \t]{1,3}(#{1,6}\s)', r'\1', text)`
in `markdown_to_html`, before `_md.markdown(...)`. 4-space indents (code blocks) are preserved.
Being a render-time fix, it also repairs already-saved reports on next open. The PDF renderer
(`report_pdf.py`) already `strip()`s each line before matching headers, so it was unaffected.

### Verification
Report 644 HTML download: raw `# Negative` paragraphs 0, summary now `<h1>…</h1>`; unit test
` # Foo`/`  # Foo`/`   # Foo` → H1, `    # x` (4-sp) → P. Restart on all 4 tenants.

## 2026-07-23 — signal reports: shorten social handles so email clients don't autolink them

### Symptom
In the alert email, account references rendered inconsistently — some as active
(broken) links, some as plain text — "especially for accounts". e.g.
`@rmounce.mastodon.social.ap.brid.gy` and `@x.bsky.social` became clickable while
`@jenom0urz` stayed text.

### Root cause
Our HTML has no `<a>` for these — the report body is link-free after `_strip_source_links`.
But email clients (Gmail etc.) **auto-linkify any bare hostname**, and ATProto/fediverse
handles carry a domain suffix (`.bsky.social`, `.eurosky.social`, `.mastodon.social.ap.brid.gy`),
so those get turned into links client-side while plain handles don't.

### Fix — `app/routes/vector_routes.py`
`_strip_source_links` now shortens social handles to a bare `@name` (drops the platform
domain suffix) for the common PDS/bridge suffixes (`bsky.social`, `eurosky.social`, `brid.gy`),
so nothing in the body looks like a hostname. `_NO_SOURCE_LINKS` directive reinforced to ask the
model for short `@handle` only. News domains (`reuters.com`, `example.org`) are untouched.
Applies to email + saved/loadable report (one strip feeds both). All 4 tenants, restart.

## 2026-07-23 — observer: only alert on social the product actually shows (on-brand ≥0.4, non-FP)

### Symptom
An observer alert (wbm instr 10) listed social posts that are **not visible in the Brand
Watcher Social tab** — e.g. two Indonesian journal-piracy "jasa unlock" X posts and a Reddit
archaeology post. The client sees an alert referencing posts they can't find/verify in the UI.

### Root cause
The Social tab gates on `topic_alignment_score >= 0.4` ("on-brand only", the platform-wide
brand-relevance standard) and hides analyst-flagged false positives. The prior social-inclusion
fix (`f2f962fb`) added social to the observer pool but applied **neither gate**, so the observer
alerted on off-brand noise (align 0.05/0.10) and on a post already flagged `false_positive`.
Measured on wbm/Wiley (14d): 444 sub-0.4 noise + 3 FP were eligible for alerting but hidden in
the tab; only 172 posts were both on-brand and shown.

### Fix — `app/routes/vector_routes.py` (all 4 observer retrieval queries)
Gate the **social branch only** (news `category IS NOT NULL` untouched) to match the tab:
`(social_meta present)` → `(social_meta present AND topic_alignment_score >= 0.4 AND NOT EXISTS
(false_positive review for this uri))`. Applied to all four observer queries (interactive,
background, entity, dedup). `bw_finding_reviews` exists on all four tenants.

### Verification
wbm observer social pool for *Brand Monitoring Wiley* (14d) now **172** (was 619) — exactly the
tab's on-brand, non-FP set. The three on-brand Bluesky posts (0.85, shown in Social) are kept;
the two X noise posts (0.05/0.10) and the FP-flagged Reddit post are dropped. py_compile clean +
restart on all four tenants.

## 2026-07-22 — signal reports: no raw source/post links (email + loadable report)

### Ask
Client-facing signal reports should not carry the raw source-post links (bsky/reddit/etc.)
— not in the emailed body and not in the downloadable/saved ("loadable") report.

### Fix — `app/routes/vector_routes.py`
Two layers, so links are suppressed at generation and stripped if any leak:
1. **Prompt directive.** `_apply_recommendations_pref` (the report-prompt finalizer both
   runners call) now also appends `_NO_SOURCE_LINKS`: *"Do NOT include any URLs, hyperlinks
   … refer to sources by @handle and platform only, never by URL"* — overrides a per-instruction
   prompt that says "link the URI" (e.g. wbm instr 10).
2. **Post-generation strip.** New `_strip_source_links(md)` removes `[text](url)`→`text`, bare
   URLs/autolinks, and the now-empty `- **URI:**`-style label lines. Applied to `report_content`
   before it is saved AND emailed, so both channels are covered from one value.
   - bugfixing/wiley/wileytest (retry variant): strip inside `_generate_report_with_retry`'s
     return; also removed the `article_uri` line from `_build_fallback_report`.
   - wbm (older, direct variant): strip at both direct `generate_response` report sites.
Our own "view full report" download link and podcast link are added during email assembly
(not part of `report_content`), so they are unaffected.

### Verification
Ran `_strip_source_links` on the real saved report 642: 5 bsky/reddit URLs → 0, empty URI
label lines → 0, Quote/Significance prose intact (5703→5338 chars). Directive append confirmed.
py_compile clean + restart on all 4 tenants. Note: already-sent report 642 keeps its links
(history); the next scheduled run generates clean.

## 2026-07-22 — observer agents: honor the instruction's configured model

### Symptom
Observer agents ran on `gpt-5.4-mini` (→ Bedrock Haiku via the yaml alias) regardless of
the model saved on the instruction. wbm's *Negative Social Sentinel — Wiley* has
`config.model = bedrock-kimi-k2-5` but every scheduled run used Haiku — pricier, and not what
the instruction was configured with.

### Root cause
`_run_signal_instruction_internal` (the scheduler's entry point) took `model: str =
"gpt-5.4-mini"` and never read `config['model']`. The scheduler
(`observer_agent_monitor.run_agent`) calls it without a `model` arg, so every scheduled run
silently used the hardcoded default.

### Fix — `app/routes/vector_routes.py`
Default the param to `None` and resolve from config:
`model: str = "gpt-5.4-mini"` → `model: Optional[str] = None`, then after loading config:
`model = model or config.get('model') or "gpt-5.4-mini"`.
Precedence: explicit caller arg > instruction's `config.model` > historic default. The
interactive runner (`_run_signals_background`) still passes `req.model` explicitly, so its
user-selected model continues to win — only the scheduler path (which passed nothing) changes.

### Verification
Stubbed `LiteLLMModel.get_instance` to capture the requested model without an LLM call: the
scheduler path (`instruction_id=10`, no model arg) now requests **bedrock-kimi-k2-5** (was
gpt-5.4-mini). Applied + py_compile clean + restart on all 4 tenants.

## 2026-07-22 — observer agents: stop excluding social posts from alerting

### Symptom
No alert emails from the wbm Observer (Explore tab). The one active agent (id 10,
*Negative Social Sentinel — Wiley*, `send_email=true → wiley@aunoo.ai`) ran daily and
succeeded but created 0 alerts since 07-13. Emails only fire when an agent creates alerts
meeting threshold (`vector_routes.py` `if config.get('send_email') and instruction_alerts
and meets_threshold`), so 0 alerts = 0 email — working as designed, but with an empty pool.

### Root cause
The observer article-retrieval queries require `category IS NOT NULL AND sentiment IS NOT
NULL`. On wbm, social posts never get a `category` (SocialEval sets `sentiment` only —
0 of 5,486 social rows have a category). So all 662 Wiley social posts in the 14-day window
were filtered out; the *Social* Sentinel was scanning only ~10 categorized news articles/day
and finding nothing negative. Long-standing (clause dates to `b4a604f6`, 2026-02), not caused
by today's collection change — re-enabling ig/tiktok just enlarged the pool being discarded.

### Fix — `app/routes/vector_routes.py` (all 4 observer retrieval queries)
Relax the requirement so social posts (which legitimately have no category) are included,
still requiring sentiment:
`AND category IS NOT NULL AND sentiment IS NOT NULL`
→ `AND sentiment IS NOT NULL AND (category IS NOT NULL OR (social_meta IS NOT NULL AND
social_meta::text <> 'null'))`
Applied to all four observer queries: interactive `run_signal_instructions`, background
`_run_signals_background`, and the entity + dedup queries in `_run_signal_instruction_internal`.
The four NON-observer queries (trend/summary/date-range stats) were left unchanged. Noise is
handled downstream as before — the LLM sentinel + threshold sift entity-collision posts
(e.g. *Maya Wiley* the politician, journal-piracy chatter).

### Verification
wbm observer pool for *Brand Monitoring Wiley* (14-day window): **10 → 672** articles, incl.
**28 Negative** candidate posts previously unseen. Applied + `py_compile` clean + service
restart on bugfixing (canonical), wbm, wiley, wileytest. `social_meta` confirmed jsonb on all
four (clause is safe). Not committed inside wiley/wileytest/wbm repos (deploy-copy model; wbm
is not a git repo). Next scheduled wbm run 2026-07-23 08:00 will scan social and email if
anything clears threshold.

## 2026-07-22 — xpoz social collection: ig/tiktok re-enable, reliability fixes, recall widening

### Summary
Instagram and TikTok social collection had silently stopped on wbm (~07-15/16); re-enabling
them exposed two collector bugs that discarded whole keyword results, plus a multi-word
query recall problem. Fixed all three in `app/collectors/xpoz_collector.py`, committed to the
canonical repo, and propagated to the other tenants. Also stood up cost monitoring and tuned
an editorial-failure monitor.

### Code — `app/collectors/xpoz_collector.py` (commit `34d8ddfd`, branch `fix/collection-reliability`)
1. **Per-platform timeout cap.** xpoz queries platforms sequentially inside one
   `keyword_monitor` call wrapped in `SEARCH_TIMEOUT_SECONDS=120`. Going from 2→4 platforms
   let a single hung platform (xpoz ig/tiktok `search_posts` can stall ~100s) push the whole
   keyword over 120s, so `asyncio.wait_for` discarded **every** platform's results — including
   posts already fetched. Fix: each `search_posts` runs via a `ThreadPoolExecutor` with
   `.result(timeout=_platform_timeout())`; a slow platform is skipped, the others' posts kept.
   - Env: `XPOZ_PLATFORM_TIMEOUT` (default `25` → worst case 4×25=100s, under the 120s wrapper).
2. **Non-blocking `client.close()`.** `close()` joins in-flight HTTP, so a still-hung platform
   thread blocked `_search_sync`'s return past 120s and the result was discarded even after the
   platform loop finished (~60s). This was the decisive bug. Fix: close in a daemon thread we
   never join (`_safe_close`). Hung platform threads are abandoned as daemons (harmless at this
   volume).
3. **Widened multi-word query recall.** Old gate required EVERY query token (AND), dropping
   ~every result for ambiguous multi-word product queries ("SAGE Publishing", "Pearson VUE").
   New gate requires only the brand **root** token; product tokens optional, leaning on the
   downstream `topic_alignment_score >= 0.4` filter to suppress the extra noise. Added
   plural/stem tolerance.
   - Env: `XPOZ_TERM_MATCH` = `root` (default, widest) / `majority` / `all` (original strict).

Note: the collection term-gate is a coarse brand-lane pre-filter; the real legit/noise
separator is the downstream 0.4 relevance filter (verified: real Elsevier/Google-lawsuit posts
score ~0.95; entity-collision noise scores <0.4 and is hidden).

### Config — wbm (`keyword_groups.social_platforms`)
Re-enabled ig+tiktok on all four `* - Social` groups:
`["twitter","reddit"]` → `["twitter","reddit","instagram","tiktok"]` (Wiley, Elsevier, SAGE,
Pearsons). Collector re-reads per-group platforms each cycle — no restart needed for this.

### Propagation
Collector fix committed in **bugfixing** (canonical). Copied file + service restart + venv
import verified on **wbm, wiley, wileytest** (all three had the file at the identical base, so
the copy = base + fixes, no divergence). Not committed inside wiley/wileytest repos (deploy-copy
model). Term-gate default is now `root` on all tenants; revert per-tenant with
`XPOZ_TERM_MATCH=all` (strict) or `=majority` (soft) in the tenant `.env` + restart.

### Verification
All four wbm groups confirmed landing ig/tiktok after the fix (Wiley +9ig/+2tiktok, Elsevier
+4, SAGE +5, Pearsons +21); zero `xpoz search timed out after 120s` in the SAGE/Pearsons run.

### Ops — wileytest social spend monitor (cost watch for `root` default)
`root` raises social volume → more Haiku social eval (`SOCIAL_EVAL_MODEL=bedrock-claude-haiku`)
+ nova-lite relevance. One-off report scheduled for the first full root day.
- Script: `/home/orochford/bin/wileytest_social_spend_report.sh 2026-07-23`
- Cron (root): `45 23 23 7 *` — emails oliver.rochford@gmail.com via Resend + logs
  `/var/log/aunoo-social-spend.log`. Compares 07-23 social volume + Haiku/nova/total spend vs
  prior-7d avg. Baseline pre-root: social ~11–44 posts/day, whole-tenant LLM ~$17–31/day.
- Revert if it spikes: `XPOZ_TERM_MATCH=all` in `wileytest/.env` + restart.

### Ops — editorial-failure monitor (saas `editorial_briefing_runs`)
Triaged an alert (run 2392, tenant 22 "Alvarovalera01"): the `fabricated_claim` verdict was a
**correct** rejection (draft over-specified an ambiguous source "two countries" into a
"US–Iran ceasefire") on a thin-signal briefing (1 correspondent). Not a bug — the LLM reviewer
worked as designed; do NOT loosen it.
Extended the regression monitor (v2→v3) to stop paging on this expected class. Added to the
WHERE clause: `AND NOT (error ILIKE '%fabricated_claim%' AND coalesce(correspondents_polled,0) <= 1)`.
Narrowly scoped — `ai_tells_above_threshold`, rich-signal (`polled>=2`) fabricated_claim, and all
other error classes still page. Session-scoped monitor (not durable).
