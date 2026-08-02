# Changes

Running log of notable operational/code changes. Newest first.

## 2026-08-02 — session-documentation tooling (skill + pre-commit reminder hook)

### Goal
This log had drifted: the newest entry was 2026-07-23 while commits ran through 2026-07-31
(`7dd5d56c`, 2026-07-31 22:56). The gap is a process problem, not a memory problem — nothing
prompted the write-up at the moment the work was fresh. Two artifacts to close it: a skill that
produces the documentation, and a hook that fires the reminder at commit time.

### `session-docs` skill — `.claude/skills/session-docs/SKILL.md` (new)
Project-scoped skill, invoked as `/session-docs`. Produces two deliverables from one evidence
pass: this file's dated feature-by-feature entry, and a product/marketing writeup under
`docs/product/`. Defaults to **pre-commit mode** — scope comes from `git diff HEAD` plus
untracked files rather than `git log`, so there is no SHA to cite yet and the skill is told to
cite paths instead of inventing or placeholder-ing one; verification must run *before* the
commit, since an entry claiming verification that happens afterwards is a false claim. It also
carries the repo's own rules: `git add -u` plus an explicit add for the new product doc but
never `git add -A` (the 2026-07-23 secret-leak entry below is why), no invented metrics, no
`git checkout` of live UI-edited state, propagation status per tenant, and don't fix code while
documenting.

### Pre-commit reminder — `.claude/settings.json` (new `hooks` block)
`PreToolUse` / `Bash` command hook. Extracts the command with `python3` (`jq` is **not
installed** on this box — the first attempt used it and failed), exits silently unless the
command contains `git commit`, then checks whether `docs/changes.md` is staged or modified. If
it is, the hook stays silent; if not, it emits `hookSpecificOutput.additionalContext` telling
the model to run `/session-docs` first, with an explicit escape hatch for trivial commits
(typo, revert, WIP, docs-only). Non-blocking by design — it never sets `continue: false`, so a
commit is never stopped. Matching is a substring test on the raw command, which is what makes
`git commit -a`, `--amend`, and heredoc forms all match; the cost is that any Bash command
merely *containing* the text triggers the check. `enabledPlugins` was preserved when the block
was merged in.

### Verification
- Hook, three cases piped as synthetic stdin: `git commit` with `docs/changes.md` untouched →
  emits the JSON; non-commit command (`ls -la`, `pytest -q`) → silent, exit 0; `git commit`
  with `docs/changes.md` modified → silent, exit 0.
- Round-trip: command re-extracted *from* `.claude/settings.json` and re-run — escaping
  survived, output parsed as valid JSON (459-char `additionalContext`), plugins intact.
- Hook proved live: it fired on a real Bash call in-session (that call's command text contained
  `git commit`) and the reminder arrived as a system-reminder.
- Skill proved discoverable: `/session-docs` loaded and this entry was written by following it.
- **Not verified**: behaviour on a genuine `git commit` — no commit was made this session.

### Propagation — none, and it cannot propagate
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

## 2026-07-31 — observer alerts mislabelled news as social; two ops monitors

Backfilled 2026-08-02. Detail below is from the commit messages except the propagation table,
which was measured on 2026-08-02.

### Observer alerts: news articles labelled "Social" — `00cb9683`
`social_ref()`'s catch-all tagged every non-Bluesky/X/Reddit match as `source · Social · view
post`, so news URLs (nature.com, cnn.com, arxiv.org…) — the bulk of observer matches — rendered
as social posts in both the alert email and the online report. Non-social URLs now carry their
publisher domain and "News", link to the site, and read "read article"; Instagram and TikTok
post URLs (xpoz platforms) are now recognised as social.
**`app/routes/vector_routes.py`**, **`app/services/email_service.py`**.

### Ops — saas email-delivery check — `9357f4f3`
One-shot verification of the three 2026-07-31 saas changes, queued via `at` for 21:00 on 08-01,
reporting each with its own verdict so a green area can't mask a red one in the subject line:
correspondent email (Newsroom-tier gate removed, 19 agents backfilled — the real signal is
matched runs that produced *no* email), the editor advisory-lock timeouts (failures against
ticks as denominator, 8.7% baseline printed alongside), and the `fabricated_claim` editorial
rejection rate against a 356-in-30-days baseline. Lock and editorial windows start at the 22:03
deploy rather than a rolling 24h so pre-fix hours don't dilute the numbers. Reads the journal
across both `saas-worker` and `saas-skills-worker`. Two dry runs shook out psql column headers
leaking into scalar values, which had also broken the empty-result fallbacks.
**`scripts/saas_email_delivery_check.sh`**; deployed to `/home/orochford/bin/`, log at
`/var/log/aunoo-saas-email-check.log`. Does not reschedule itself.

### Ops — collector health check, tracked copy resynced — `7dd5d56c`
The tracked copy and `/home/orochford/bin/collector_health_check.sh` (the one root's `*/30` cron
executes) had diverged, so version control did not hold what was live. The gap was one comment
line recording abbott's removal from `TENANTS` at its 07-16 shutdown; behaviour identical either
way. Direction was tracked ← live, since live is what runs and carried the extra context.

### Propagation (measured 2026-08-02, md5 vs canonical)
`vector_routes.py` and `email_service.py` are identical on wiley and wileytest — the observer
labelling fix is on both.

## 2026-07-30 — post-Bedrock breakage sweep (11 fixes)

Backfilled 2026-08-02. A day of failures that all trace to the same root: the Bedrock migration
moved every tenant off OpenAI, and code that still assumed OpenAI models, OpenAI-shaped JSON, or
a `python` on PATH broke quietly. Detail from the commit messages; propagation measured
2026-08-02.

### Enrichment: retry on empty/unparseable response — `c6bb7a84`
Reasoning models (Kimi/Nova on Bedrock) intermittently return content the Key:Value field parser
can't read — roughly 1 in 8 per the commit message — which marked the article
`enrichment_failed` on a single miss (`Available fields: []`). `generate_response` + parse is now
wrapped in a 3-attempt retry so a transient bad response recovers instead of failing the
article. **`app/analyzers/article_analyzer.py`**.

### Event-loop watchdog SEGV — `7258071e`
The watchdog armed `faulthandler.dump_traceback_later(all_threads)` every cycle; when the loop
blocked >8s it walked every thread's `PyThreadState` from a timer thread, racing native-extension
execution and thread teardown, and SEGV'd inside `_Py_DumpTracebackThreads` (crash IP `0x4bb854`,
`segfault at 0x70`). It crashed wileytest twice on 2026-07-30 during enrichment + hybrid
relevance. The C-level watchdog is now behind `EVENT_LOOP_WATCHDOG=1`, **default off**; the async
lag WARNING, ring buffer, and the admin endpoint's GIL-safe Python-level
`dump_all_thread_stacks()` still give diagnosis without the crash.
**`app/utils/event_loop_monitor.py`**.

### Add-Topic wizard: LLM suggestion dead on Bedrock tenants — `3f6302c2`
`/api/onboarding/suggest-topic-attributes` scanned `litellm_config` for the first `openai/` model
with an API key and raised "No OpenAI model configured" when none existed — always the case after
the Bedrock migration, so the wizard silently stopped using the LLM. Now resolves a bare alias via
`resolve_litellm_call_params` and defaults to a Claude alias (Nova emits unreliable structured
JSON). **`app/routes/onboarding_routes.py`**.

### Foresight model dropdown: real models, not aliases — `1ddef137`
`litellm_config` exposes ~two dozen aliases (`gpt-*`, `gemini-*`, `mixtral-*`, `claude-*-latest`)
that all collapse onto Claude Sonnet 4.5 / Haiku 4.5 plus Nova Pro/Lite and Kimi. The `/models`
endpoint dumped all of them — mislabelling Claude as GPT/Gemini, duplicating entries, and a
fallback that mapped id `gpt-5.4` to labels "GPT-4.1"/"GPT-4o". Returns the 5 distinct underlying
models with honest labels. **`app/routes/trend_convergence_routes.py`**.

### Trend convergence: org profile never loaded + brittle JSON parse — `f27e8bb8`
`get_organisational_profile` returns a SQLAlchemy mapping keyed by column name; the route accessed
it positionally (`profile_row[0]`) → "Could not locate column in row for column '0'", so the
profile silently never loaded. Now accessed by name, tolerating JSON-text or already-decoded JSONB.
The AI-response JSON extraction used a naive non-greedy regex / first-`{`-to-last-`}` scan that
500'd on nested objects or trailing prose; it now routes through the shared `_preprocess_response`
and `json.raw_decode`, 500-ing only when nothing parseable remains, and the outer `except` no
longer re-wraps the `HTTPException`. **`app/routes/trend_convergence_routes.py`**,
**`requirements.txt`**.

### Collectors — `4bd1aa45`, `1c09aebf`
NewsFirehose: publisher/keyword names containing `&` ("John Wiley & Sons", "Taylor & Francis")
reached the `/v1/search` tsquery builder and raised `PostgresSyntaxError` (500); `_normalize_query`
now drops literal tsquery operator chars (`& ! : * \`) so terms degrade to plain words.
TheNewsAPI: `keyword_monitor` passes `search_fields` as a comma-separated string and
`",".join(str)` iterates characters, producing `search_fields=t,i,t,l,e,,,d,…`; a string is now
split into a list first, as `newsapi_collector` already did.

### Ingest and services — `0bbbc7db`, `28fe09d2`, `0ab6a203`, `9876623c`
Hybrid relevance scoring: `article_data` content/summary keys can be present with an explicit
`None`, so `.get(k, '')` still returned `None` and `len()` raised — coerced with `or ''`. Firecrawl
batch scrape now skips the call (which 400s "No valid URLs provided") on an empty or all-invalid
URL list. Data-quality check parsed the LLM reply with `json.loads`, throwing "Extra data" when the
model appended prose — now starts at the first `{` and uses `raw_decode`. Brand-watcher auto-retrain
shelled out to `python`, which does not exist on these hosts (only `python3` / the venv), failing
with Errno 2 — now uses `sys.executable`. Analysis cache: long URLs (Google-News RSS article IDs)
produced filenames over the 255-char limit (Errno 36, silent cache-write failures) — the URL portion
is capped and a SHA1 of the full URL appended, so short URLs keep their names and no cache
invalidates.

### Briefing Desk: model pinned server-side — `e79b7aa3`
Daily-briefing draft/incident-detection and final synthesis now read the model from
`emerging_topics_settings.model`, overriding the browser dropdown, so composed content and the
`model_used` byline are tenant-consistent. Falls back to the client-passed model when unset.
**`app/routes/daily_reports_routes.py`**, **`app/services/daily_briefing_compose_service.py`**.

### Propagation (measured 2026-08-02, md5 + marker grep vs canonical)
All files identical on wileytest. On wiley, all identical **except two**:
- **`trend_convergence_routes.py` — wiley was MISSING `1ddef137`** (remediated 2026-08-02, below).
  It carried the old alias list (`{'id': 'gpt-5.4', 'name': 'GPT-4.1'}`, 2 hits of the `'GPT-4.1'`
  label; canonical and wileytest had 0) and was 3869 lines vs 3831. It *did* have `f27e8bb8` —
  both the by-name `profile_row['id']` access and the `raw_decode` path — which dates wiley's copy
  to between 16:05 and 16:24 on 07-30, i.e. it was taken 18 minutes before the dropdown fix landed.
  Wiley's foresight model dropdown was showing fictitious GPT/Gemini entries for three days.

  **Remediation, 2026-08-02.** `diff -u` against canonical showed exactly **one hunk**, confined to
  the `/api/trend-convergence/models` endpoint — no wiley-local divergence anywhere else in the
  file — so a wholesale file copy was safe rather than a surgical hunk apply. Backed up wiley's
  copy off-tree, copied canonical over it (both now md5 `30b0c46e`), `py_compile` clean under
  wiley's own venv, `sudo systemctl restart wiley.aunoo.ai.service` (active 10:38:53 CEST).
  Verified live: `curl http://127.0.0.1:10006/api/trend-convergence/models` returns the 5 real
  models (Claude Sonnet 4.5, Claude Haiku 4.5, Nova Pro, Nova Lite, Kimi K2.5) and the
  `'GPT-4.1'` label count is 0. Not committed in wiley — deploy-copy tree.
- `automated_ingest_service.py` differs by 61 lines but **has** the `0bbbc7db` `or ''` guard at
  line 447 — that diff is unrelated tenant drift, not a missing fix.

Adjacent, not a propagation gap: one positional `profile_row[0]` remains in this file on **all
three** tenants including canonical — a different code path `f27e8bb8` did not touch. Flagged,
not changed.

## 2026-07-30 — EU AI Act Article 50: label AI-generated output — `25812e69`

Backfilled 2026-08-02.

`app/compliance/ai_disclosure.py` added as the single source for both the visible "AI-generated"
disclosure and the machine-readable marker, wired into email (opt-in `X-AI-Generated` header plus
footer), HTML/PPTX/DOCX/PDF reports, dashboard exports, and the in-app React dashboards. The
over-claimed "reviewed and validated" UI copy was softened at the same time. Touches 18 service
files plus the React build and templates.

### Propagation
`ai_disclosure.py` identical on wiley and wileytest (measured 2026-08-02). Per
`project_euaiact_art50_compliance`, this also shipped to the saas side (canonical `saasmvp-app`,
commit `4ef4930`) — not re-verified here.

## 2026-07-29 — enrichment loss: parser, prompt, and the relevance gate

Backfilled 2026-08-02. The single highest-impact day in this range: news articles were being
enriched, then silently discarded, then made permanently invisible. Measurements below are from
the commit messages; propagation measured 2026-08-02.

### Root cause: parser discarded whole analyses over heading variants — `b266238c`
`parse_analysis()` validated the model's response by exact heading match on 14 required fields.
When a model relabelled a heading ("Driver Signal Explanation"), numbered them ("1. Category" —
which the prompt's own numbered list invited), wrapped them in markdown, collapsed the four
rationales into one "Explanation" block, or omitted "Title", **the entire analysis was thrown
away** and the row kept NULL `category`/`sentiment`.

Every observer agent retrieves on `sentiment IS NOT NULL AND category IS NOT NULL`
(`vector_routes.py`), so those articles became invisible to signal alerts, `/explore` and reports
— **permanently, since nothing retries them**. On wileytest this was ~227 news articles a day.
Social posts enrich on another path and were unaffected, which is why agent output had skewed
toward Bluesky.

The parser now strips list markers and markdown from headings *and* values (a leading `**` on a
value reached the ontology check as `** Widespread adoption` and got downgraded to "Other"),
aliases known heading variants onto canonical names, reuses a merged "Explanation" block for the
per-field rationales, falls back to the caller's title when "Title" is absent, and hard-fails only
on Title/Summary/Category/Sentiment — descriptive fields now warn and store blank instead of
voiding the record. `scripts/reenrich_parse_failures.py` added to recover the backlog; it
preflights each topic's ontology and skips topics with an empty list, since `analyze_content()`
rejects those before calling the model — wileytest's "M&A Updates" has no `future_signals`, which
blocks 3,003 articles on config grounds rather than parsing.
Also isolates `PromptManager` storage in tests: `PromptTemplates.load_custom_templates()` calls
`save_version()`, so running the suite had been overwriting live `data/prompts/current.json` with
the test fixture's placeholder prompt.

### The prompt that invited the drift — `8712c41c`, then `3f37ef27`
Six defects in the analysis prompt, each mapping to a failure in the logs: two competing "Format
your response as follows:" blocks (the first listing only "Summary:", so a model anchoring on it
emitted nothing else); sections numbered 1–8 echoed back as headings; section 8 titled "Relevant
tags" against a "Tags:" output label; "Title" never requested in the instructions at all (the
largest single missing field); "Provide a brief explanation" without naming the target field,
inviting one merged block instead of four labelled ones; and "regarding the future of AI" on every
topic including M&A Updates and Geopolitical Hotspots. Replaced with unnumbered sections keyed to
exact field labels, one output block, and an explicit instruction against numbering, markdown and
renaming. A/B on the same 12 articles with `bedrock-kimi-k2.5`: old 10/12 clean with 2 drifted
(exactly the failure modes dominating the production logs), new 12/12 clean.
Written via `PromptManager.save_version` (v1.0.3 → v1.0.4) on bugfixing, wileytest and wiley; all
three reported template hash `ec7112190aee`. `get_template_hash` feeds the analysis cache key, so
cached analyses under the old prompt invalidate on their own.

`3f37ef27` then fixed the *hardcoded* default too. `8712c41c` rewrote
`data/prompts/content_analysis/current.json`, which is what existing tenants run, but
`PromptTemplates.DEFAULT_TEMPLATES` still carried every defect that rewrite removed.
`initialize_defaults()` only seeds when no stored version exists, so this changes nothing for an
existing tenant — it matters for a **newly cloned** one, which would otherwise start life with
exactly the prompt that was causing analyses to be discarded, the bug reappearing silently months
later on a fresh deployment.

### Relevance gate: the CE tier was one flag away from an outage — `128d037a`, `540584d4`
`RELEVANCE_USE_CE_TIER` is off by default, and that default was the only thing preventing a serious
outage. Against a 49-item hand-labelled gold set on wileytest (20 relevant / 29 name collisions),
relevant articles scored min 0.000018 / median 0.0029 / max 0.80 while collisions scored min
0.000016 / median 0.000018 / max 0.0049 — so the shipped `CE_LOW=0.10` sat *above 90% of the
relevant population*, and enabling the flag would have "confidently rejected" 18 of 20 relevant
articles with no LLM review at all. There is no honest reject threshold: the widest cut losing no
positive is 0.000018, which *is* the lowest positive — a coincidence, not a margin.

The tier is accept-only now. The risk is asymmetric — a wrong confident accept costs one enrichment
call, a wrong confident reject drops the article permanently, the same failure mode that made news
disappear from the observer agents. `CE_HIGH` dropped 0.90 → 0.05, an order of magnitude above the
worst collision (0.0049, "Sage Group (OTCMKTS:SGPYY)" — the accounting-software firm, not SAGE
Publishing). On accept, the hybrid score is raised to the threshold rather than overwritten with the
CE value, whose scale is not comparable to the embedding/classifier scale.

`540584d4` then **corrected its own predecessor's measurement**. `128d037a` justified the tier with
"AUC 0.907, better than any reworded query"; that scored **titles only**, while
`_compute_cross_encoder_score` builds `f"{title}. {summary}"` — and 4 of its 20 positives were
hand-written titles rather than real rows. Re-measured on real articles with real summaries in the
production document form: **theme topics AUC 0.885** (199 relevant / 114 not, weak-labelled from the
pipeline's own confident extremes), **brand topics AUC 0.478** (9 relevant / 86 not, hand-labelled).
Rewording does not rescue the brand case (bare entity 0.298, "news about X" 0.425, question form
0.402, "X the company" 0.609, raw topic 0.478) because the task there is entity disambiguation —
SAGE Publishing vs Sage Group plc vs sage the herb vs sage-agent-sdk on PyPI — a named-entity
problem a semantic reranker rates alike. So the tier is now theme-topics-only. Flag still defaults
off; this makes it safe to turn on, it does not turn it on.

Noted in `540584d4` and still open: the gate uses its own brand predicate because the existing
`is_brand_topic` only matches "Brand Monitoring X" and misses the live "X - Brand Watch" topics
(78 articles, most recent 2026-07-27). The narrower predicate was left alone rather than silently
changing which topics the classifier-confidence guard covers.

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
