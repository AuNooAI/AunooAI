# Ingest fix implementation log

What was built against [08_INGEST_FIX_SPEC.md](08_INGEST_FIX_SPEC.md) and
[08c_PIPELINE_FAILURE_FIXES_SPEC.md](08c_PIPELINE_FAILURE_FIXES_SPEC.md) on 7 October 2026, on
branch `fix/ingest-pipeline-spec` (from `83fecd57`). Nothing here is deployed: the bugfixing
service still runs the code it started with at 10:03. The three migrations below are applied to
the bugfixing database (`test`) only.

## Commits

| Commit | Work |
|---|---|
| `467100a8` | WP1 / M1: firehose paging, checkpoints, gaps, follow-up rounds, health |
| `d25b0f57` | WP3a, WP3b, WP6 / M3: scrape after the gate, auto prompt, cache key, output lock, parser; WP5d attempt guard |
| `9332ce13` | WP2: documentation corrections (describe the code at `83fecd57`) |
| `0d0ff460` | WP4 / M2, WP5a-c and e / M4-M5, social embeddings and agent evidence, Reddit pause |
| `eff711f2` | WP7: matched search term reaches ingest |

Two commits from another session (`9ba6ce37`, `7cdd2647`, Market Monitor) also landed on this
branch, because the shared tree is checked out on it.

## Migrations (apply in this order, before restarting onto the code)

- `ip_001` checkpoint `scheduled_through`, `progress_at`, `no_progress_runs`, `next_attempt_at`;
  table `collection_gaps`.
- `ip_002` relevance decision evidence on `articles` and `keyword_article_matches`; relevance
  retry columns.
- `ip_003` embedding repair state on `articles`.

The new code reads these columns in the readable-articles rule and the social evaluator, so a
site must have all three before it runs this branch. All are additive; the old code ignores them.

Prompt migration: run `scripts/migrate_analysis_prompt_schema.py` on each site (dry run first).
It gives the live `content_analysis` prompt the fixed block and seeds `content_analysis_auto`.
Without it the prompt screen can no longer save the manual prompt.

## What changed, by package

**WP1 / M1.** Firehose pages every chunk to `has_more: false` or past the window; no per-chunk
cap; malformed paging is a failure; resume replays one page and never walks the cursor back;
dates go out as UTC days with slack and rows are filtered to the exact interval (the API refuses
datetimes, so full timestamps cannot be sent); failures keep earlier pages' items. Proven
coverage moves only on a complete run; the stall valve is gone; a list API's full page records a
gap and moves `scheduled_through` (policy `COLLECTION_NON_EXHAUSTIVE_POLICY`, default
`advance`); failures and non-progressing runs back off; quota failures wait for the pause end.
The monitor saves each round before committing and gives a moving cursor up to 2 more rounds.

**Too-broad keywords.** Measured on 7 Oct: the 76 stuck firehose keywords return about 54,700
rows for one 24-hour window (the site's late-September intake was 540-730 a day). A chunk with
more than `NEWSFIREHOSE_BROAD_PAGES_PER_DAY` (20 since `c00cc3f6`) pages per day of window now fails as a
configuration fault with no items. Most AI-group keywords exceed it: their OR-flattened queries
contain `AI` on its own.

**WP2.** See commit `9332ce13` and `08b_ARTICLE_TEXT_RECIPIENTS.md`.

**WP3a.** Only snippets under 80 characters (and brand topics, whose decision reads the page)
are scraped before the gate; the rest after passing. 2,252 of 3,344 non-brand pages in the 7
days to 7 Oct belonged to articles the gate rejected.

**WP3b / WP6 / M3.** `content_analysis_auto` prompt (no bias or factuality fields), no date call
in auto mode, a cache key covering mode, lists, prompt and schema version; a fixed
`REQUIRED OUTPUT FORMAT:` block enforced by PromptManager on save, restore and import (HTTP
422); known-header parsing; required labels validated inside the 3-attempt loop. Page input is
built but off (`ANALYSIS_INPUT_MODE=summary_first`).

**WP4 / M2.** One threshold for both gates; Jev and CE accept without clamping; decisions
stored; readers honour them, exclude failed states, and keep the legacy rule for old rows.

**WP5 / M4 / M5.** Analysis attempts have a deadline and an ownership token (a late thread
neither caches nor returns). Relevance failures store NULL scores and retry with a cap. The retry
sweep is fair and locked. Vector upserts report failures; `embedding_repair` embeds approved news
and relevant social posts. Health alerts on overdue embeddings and exhausted retries.

**Social visibility.** Relevant social posts get embeddings (vector search and Auspex then find
them); incident tracking and real-time signals accept them through `agent_evidence_sql()`.

## Not done

- WP3c social model routing: needs the 200-post comparison.
- WP6a 300-article replay and the 50 non-English checks: page input stays off until then.
- WP7 still open: provider identity (needs a key migration plan), `daily_request_limit`
  (enforce or label as not enforced: enforcing the site's 1,000 a day would stop firehose
  collection), the per-group settings that do nothing, and removal of the obsolete enrichment
  services. Done in `e0370e1b`: run write counts, dedup priority, label-list checks, read-only
  MBFC lookup, daily cache cleanup, `NEWSAPI_KEY`. Done by another session: all-groups
  check-now routing, `topic='general'`, `submission_date`.
- WP3b token measurement and WP3a replay sample: need live traffic after deployment.
- Brand Watcher readers with user-set sliders (`:min_rel`) and the Swiss project's `:social_min`
  keep their own floors on purpose; `training_routes` (0.5) serves training data.
- `contracts.py` is no longer identical to the SaaS copy.
