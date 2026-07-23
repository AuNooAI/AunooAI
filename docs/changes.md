# Changes

Running log of notable operational/code changes. Newest first.

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
