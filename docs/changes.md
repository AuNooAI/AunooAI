# Changes

Running log of notable operational/code changes. Newest first.

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
