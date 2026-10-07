# Stuck newsfirehose checkpoints: investigation

> **Status, 7 Oct 2026:** fixed in commit `a7b3263d` on bugfixing, copied to abm and bwtemplate. The firehose collector now pages the API (100 per page, a 3-page cap per OR-chunk that only counts pages inside the window), returns failures instead of empty successes, and sends `to_date` as the following day. A page cap advances the checkpoint, and a stall valve advances any non-failing window that ended 72 hours ago. The health route alerts once per provider on stalled scopes. The investigation below is as written before the fix, with the corrections the review made.

Date: 2026-10-07. Read-only investigation: no edits, restarts or commits. SQL was SELECT-only. I sent a handful of read-only GET requests to the live NewsFirehose API (188.40.128.115:8000) to check paging and date handling.

## Summary

Since 2 October, newsfirehose has stopped collecting new articles for 82 keyword scopes on bugfixing and 9 on abm. Commit 6f8d4fbd (1 Oct 2026, "Collector data quality") brought in fixed collection windows and a rule that a full page of results does not prove the window is complete. The commit gave paging to TheNewsAPI, NewsAPI, NewsData and the others, but it never touched `newsfirehose_collector.py`. Firehose therefore falls back to the generic single-page `collect()` in the base class. Any keyword with 10 or more hits in its window returns a full page. The run is then recorded as "success, coverage incomplete", the checkpoint counts it as a failure, and the next run searches the same frozen window again, with no end. Nothing gives up, backs off or raises an alert.

The damage is large and is getting worse. The "AI" group has gone from about 100 to 180 new keyword-matched articles a day to zero since 5 October. Geopolitical Hotspots has dropped from about 150 to 200 a day to 13 to 40. SOC Automation Market Watch has dropped from about 35 to 80 a day to 0 or 1. The number of full-page runs per day has grown from 119 to 158, because any scope that gets a busy window joins the stuck set and never leaves it.

The firehose API already supports `page` and returns `has_more`, so the fix the spec asked for (page through the window, return a partial result with a continuation) is possible today. A second, smaller bug sits in the same collector: it sends `to_date` as a bare date, and the server reads that as midnight at the start of the day. An interval that starts and ends on the same calendar day therefore searches a single instant.

## 1. Which commit started this, and what the old code did

**The commit is 6f8d4fbd** (2026-10-01 22:31 +0200, "Collector data quality: outcomes, identity, dates, shared quota, backoff, health"). `git log -S'list API returned a full page'` and `git blame` both point at it for `app/collectors/base_collector.py:263-266`. The same commit also introduced `app/services/collection_runs.py` (claim and commit), `CollectionResult.may_advance_checkpoint` in `app/collectors/contracts.py`, and the claim/commit flow in `app/tasks/keyword_monitor.py`. The commit message says bugfixing was restarted on this code. The first newsfirehose checkpoint on bugfixing is dated 2026-10-02 01:53, which matches.

**Firehose was never given paging.** `app/collectors/newsfirehose_collector.py` does not appear in the commit's file list. Spec section 3 (`docs/COLLECTOR_DATA_QUALITY_SPEC.md:124-140`) asks for page or cursor traversal per provider, with partial status and a continuation when the budget runs out. It also says "Providers that cannot offer exhaustive search report that limitation." TheNewsAPI got that treatment (`thenewsapi_collector.py` pages, stops when `found` is exhausted, and otherwise returns `partial` with `{"page": n}`). Firehose did not, so it inherits the base default, which reports every full page as incomplete.

**The old code did not use windows at all.** Before 6f8d4fbd, `keyword_monitor.py` computed `start_date = now - search_date_range` (7 days) on every run (old line 652). It called `collector.search_articles(... max_results=page_size, start_date=start_date)` with no end date, so the server searched up to now. It took the top `page_size` (10) results, newest first, and moved on. A full page was simply the 10 newest articles. Anything beyond 10 per run was lost, but every run saw fresh articles. No coverage state was kept.

## 2. What happens on the next claim

**The same window is searched again on every run, with no end.** The chain in the code runs as follows:

- `base_collector.py:263-266`: if `len(items) >= max_results`, it sets `coverage_complete=False` and `truncated_reason=provider_limit`, while `status` stays `success`.
- `contracts.py:190`: `may_advance_checkpoint` requires `coverage_complete`, so it returns False.
- `collection_runs.py:262-283` (`commit_interval`): the first branch needs `may_advance_checkpoint`, so it is skipped. The second branch needs `status == "partial"` or a retryable failure, so it is also skipped. The `else` branch then increments `consecutive_failures`, writes a NULL `last_error_code`, and leaves `interval_start`, `interval_end` and `coverage_through` untouched.
- `collection_runs.py:140-224` (`claim_interval`): `has_unfinished_interval` is true (`coverage_through < interval_end`, or NULL), so the claim returns the same stored interval. The lookback cap (`now - lookback`) only applies when a new interval is being opened, so it never fires for a stuck one.

**Nothing gives up, backs off or alerts.** Nothing backs off on `consecutive_failures`. The health route does list scopes with three or more failures under `pending_intervals` (`collection_runs.py` `health_summary`, `GET /api/health/collection`): 84 rows on bugfixing on 7 Oct. Its alert, though, aged each scope by `updated_at`, which every claim and commit refreshes, so none of the 84 could ever alert.

**A second, latent hole (found in review).** `search_articles` swallowed every HTTP error and exception and returned an empty list. The default `collect()` then reported success with zero items, complete, and the checkpoint advanced past a window nobody had searched. It had not happened yet (no firehose errors in the journal since 2 Oct), but any 4xx, 5xx, 429 or timeout would have skipped a window silently.

**Each run re-finds the same 10 articles and inserts nothing.** The firehose collector sorts by `published_at` descending (`keyword_monitor_settings.sort_by = publishedAt`) inside a fixed `[from_date, to_date]`, so it returns the same top 10 every time. Two examples from `collection_runs`:

| scope | stuck window | runs since stuck | received per run | inserted |
|---|---|---|---|---|
| kw:404 "SOC automation" | 2026-09-25 08:53 to 2026-10-02 08:53 | 10 (twice a day, 2–6 Oct) | 10 | 0 |
| kw:190 Geopolitical "president…" | 2026-10-02 05:24 to 2026-10-02 17:25 | 10 | 10 | 0 |

The service log for kw:190 at 2026-10-07 05:48 shows the same picture: "Found 10 unique articles… Rejected-candidate ledger: 9/10 URLs already rejected by group 10; skipping their relevance scoring". The rejected-candidates ledger keeps the repeat cost low (about one LLM relevance call per run, not ten), but nothing new comes in.

Of the 82 stuck scopes on bugfixing, 46 have never advanced at all (`coverage_through IS NULL`; their first 7-day window was already full). The other 36 advanced once or more and then hit a busy 12-hour window. One stuck scope has no matching `monitored_keywords` row, so it is an orphan.

**A second bug: firehose `to_date` drops the last day.** The collector sends `to_date=end_date.strftime('%Y-%m-%d')`, and the server applies `published_at <= to_date`, which means midnight at the start of that day in the server's time zone (+02). I checked this live:

- `q=SOC automation, from=2026-10-01, to=2026-10-01` returned 0 results, although articles from 1 October exist.
- For kw:190's chunk, `from=2026-10-02, to=2026-10-02` returned 10 results, all stamped `2026-10-01T22:00Z`. That is local midnight, which is how firehose stores articles that only have a date. With `to=2026-10-03`, all 10 results were stamped `2026-10-02T22:00Z`.

So a 12-hour interval that starts and ends on the same day searches one instant: midnight. For broad queries, that instant alone holds 10 or more date-only articles, so 14 of the stuck scopes are stuck on a window that is effectively one instant wide. Intervals that cross midnight do cover the earlier day, which is why this bug did not lose data before the full-page rule arrived. It still needs fixing alongside the main defect.

## 3. Impact on bugfixing

**The `articles` table has no column that records the provider.** `collector_source` is set in memory (`keyword_monitor.py:547`) but never stored, and the provider column in `article_observations` holds domains. So I measured by keyword group instead: new articles (`first_seen_at`, UTC day) joined to `keyword_article_matches.group_id`. Groups 9, 10, 16 and 34 use only newsfirehose (the global `providers = ["newsfirehose"]`), so for them this measure is close to firehose yield.

| day | g9 AI | g10 Geo | g16 SOC MW | g33 EV news | g34 EV cells MW | unaffected Swiss/EU (21–25) |
|---|---|---|---|---|---|---|
| 09-25 | 167 | 205 | 80 | 1 | 0 | 42 |
| 09-26 | 181 | 177 | 52 | 0 | 0 | 26 |
| 09-27 | 101 | 150 | 35 | 0 | 0 | 44 |
| 09-28 | 104 | 150 | 39 | 1 | 0 | 68 |
| 09-29 | 169 | 179 | 74 | 2 | 1 | 39 |
| 09-30 | 0 | 0 | 0 | 0 | 0 | 14 |
| 10-01 | 72 | 155 | 15 | 171 | 35 | 28 |
| 10-02 | 135 | 27 | 105 | 285 | 142 | 26 |
| 10-03 | 82 | 164 | 3 | 21 | 2 | 13 |
| 10-04 | 8 | 13 | 0 | 7 | 0 | 5 |
| 10-05 | 0 | 17 | 1 | 38 | 2 | 11 |
| 10-06 | 0 | 20 | 1 | 39 | 0 | 18 |
| 10-07 (part day) | 0 | 40 | 0 | 0 | 0 | 18 |

Notes on the table:

- 30 September is a separate outage that day; it predates the new code.
- The spikes on 1–2 October come from groups 33 and 34, which were new, plus first-contact 7-day windows. A first window inserts its 10 articles once and then sticks.
- The Swiss/EU groups have no stuck scopes, and they stay roughly level. Groups 9, 16 and 34 fall to almost nothing.

**Stuck scopes by group (newsfirehose, `consecutive_failures > 0`):**

| group | name | stuck / firehose scopes | max failures | window frozen at |
|---|---|---|---|---|
| 9 | AI | 25 / 25 | 10 | 2026-10-02 |
| 33 | EV Battery Industry - News | 18 / 24 | 10 | 09-25 to 10-02 |
| 34 | EV Battery Cells - Market Watch | 15 / 24 | 10 | 09-25 to 10-02 |
| 16 | SOC Automation - Market Watch | 12 / 131 | 10 | 09-25 to 10-02 |
| 10 | Geopolitical Hotspots | 11 / 22 | 10 | 2026-10-02 |
| 21–25 | Swiss / EU elections | 0 / 56 | – | – |

Every keyword in the AI group is stuck. On the API side, "SOC automation" alone has 38 firehose results between 2 and 7 October that bugfixing never asked for (`from=2026-10-02&to=2026-10-07&page_size=100`). Run volume per day shows the problem spreading: full-page runs went from 119 (10-02) to 133 (10-03) to 158 a day (10-04 to 10-06). "Complete" runs return about 30 items a day across roughly 400 runs, partly because of the `to_date` bug.

Other providers on bugfixing: xpoz has 3 stuck scopes from the same full-page rule, which xpoz copies in its own `collect()` (`xpoz_collector.py:466-469`). Telegram is clean, because its social page floor of 25 is rarely filled. Reddit has 2 scopes failing on quota, which is a real error and not this defect.

## 4. Firehose page size and paging

- **The page size comes from tenant config.** It is 10, from `keyword_monitor_settings.page_size` (one row; `sort_by=publishedAt`). `keyword_monitor.py:503` passes it as `max_results`. Only reddit, bluesky, xpoz and telegram get the `SOCIAL_PAGE_SIZE` floor of 25.
- **The collector already supports larger pages.** It sends `page_size=min(max_results, 100)` and `page=1` (`newsfirehose_collector.py:205-206`). It merges OR-chunks of at most 8 terms (an API limit), stops once it has `max_results*2`, then cuts the list to `max_results` (line 377). Because of that cut, a full page is almost certain whenever at least 10 matches exist.
- **The API supports paging and says when the end is reached.** `/opt/newsfirehose/api/routers/search.py:98-108,263-296` takes `page_size` 1–100 and `page` ≥ 1, uses `LIMIT page_size+1 OFFSET`, and returns `has_more`. I confirmed this live: page 1 and page 2 of the stuck "SOC automation" window both returned 10 rows with `has_more=true`. With `page_size=100`, the call returned 50 rows with `has_more=false`. So the whole stuck window holds 50 articles and could be finished in one request. `has_more=false` is a proven end, which is exactly what the base class says list APIs lack. The collector currently throws that flag away.
- **Paging limits.** The API is rate-limited to 100 requests a minute and has a 60-second statement timeout. The OFFSET paging is newest-first over a fixed window, so an article indexed late can shift a page boundary. That can cause a duplicate (dedup handles it) or, rarely, a skip. The spec accepts "overlap plus dedup".

## 5. Other tenants on the same code

The full-page lines exist only in three tenant trees: bugfixing, abm and bwtemplate. I checked every `tenants/*/app/collectors/base_collector.py`. wiley, wileytest, oviva, sunstar, panaya and the rest do not have this code yet.

| tenant | DB | service | stuck newsfirehose | other |
|---|---|---|---|---|
| bugfixing | test | active | **82** of 286 (max 10 failures) | xpoz 3, reddit 2 (quota) |
| abm | abm | active | **9** of 28 (8 at 10 failures, 1 at 9) | xpoz 7 (5 full-page stalls, 2 timeouts), reddit 19/19 (quota) |
| bwtemplate | bwtemplate | inactive | 0 (table empty) | – |

The 9 stuck abm firehose scopes are "Palantir Technologies", Palantir (2 scopes), PLTR, Feedly (2), "Feedly AI" and Meltwater (2). All have windows frozen at 09-25/26 to 10-02/03, and none has ever advanced (`coverage_through` NULL). abm is therefore missing all new firehose coverage for its main brands since 2 October. The 7 stuck xpoz scopes cover the same brands plus Signal AI and "Palantir Foundry". Five of them stall on the same full-page rule, and two show a real `timeout`.

The saas databases (`aunoo_saas_prod`) also have a `collection_checkpoints` table, but the saas code does not contain this rule. Its failing scopes carry real error codes (crossref `http_4xx`, openalex `quota_exhausted`, sec_edgar `http_5xx`), which is a different issue.

**Any tenant that receives 6f8d4fbd will hit this within a day.** Copying the code to wiley or wileytest before fixing it would reproduce the stall on paying-customer data.

## 6. Recommended fix

### Options

**(a) Page through the window in the firehose collector and return partial with a continuation.** This is what the spec asked for, and it is what I recommend.

- Pros:
  - Collection is complete, and `has_more=false` gives a real proof of completeness.
  - The existing `partial` branch of `commit_interval` already stores the continuation without counting a failure.
  - It uses the existing `page_budget()`, `provider_max_pages()` and `PageClock` helpers, the same way TheNewsAPI does.
- Cons:
  - More code than (b) or (c), because the OR-chunk loop needs a two-part cursor `{chunk, page}`.
  - Busy keywords make more requests per run. Firehose is our own API, so this costs server load, not money.
  - More articles reach the relevance step. The rejected-candidates ledger limits repeats, but the first pass over a large backlog costs LLM calls (kimi or nova-lite).

**(b) Advance anyway on a full page (the old behaviour, but recorded).**

- Pros: a few lines, and every stuck scope recovers on its next run.
- Cons:
  - Quietly drops everything beyond the top 10 per interval, which is the loss the spec was written to stop.
  - Done naively by setting `coverage_complete=True`, it would also hide the truncation from the run records.

**(c) Raise `page_size` to 100.**

- Pros: one config value, no code.
- Cons:
  - `page_size` is shared by every news collector. TheNewsAPI quota use would rise, and every collector would feed more articles into enrichment.
  - Any scope with 100 or more hits in a window still sticks forever. The "AI" OR-chain queries are the likely cases.
  - It does nothing for xpoz, telegram or opoint.

### Recommendation

Fix this in three parts, in order:

1. **Do (a) for newsfirehose and fix the `to_date` bug in the same change.**
2. **Do a recorded version of (b) as the rule for collectors that cannot page** (telegram, opoint, xpoz). The checkpoint advances, but the run record still says `coverage_complete=false, truncated_reason=provider_limit`. This matches the spec's line "providers that cannot offer exhaustive search report that limitation."
3. **Add a safety valve and an alert**, so the next defect of this kind cannot stall a scope silently. After N consecutive non-advancing runs on the same window (for example 6, which is three days at 12-hour checks), advance the checkpoint, set `coverage_unknown_before` and log a warning. Also have `/api/health/collection` count scopes where `consecutive_failures >= 3`.

Option (c) is not recommended on its own.

### Code locations

- `app/collectors/newsfirehose_collector.py:154-380` (`search_articles`), which needs a new `collect()` override, plus `:236-240` (the `to_date` value).
- `app/collectors/base_collector.py:263-266` (the full-page rule) and `app/collectors/contracts.py:55` and `:187-190`.
- `app/collectors/xpoz_collector.py:466-469`, which duplicates the rule.
- `app/services/collection_runs.py:262-283` (`commit_interval`) and `:184-193` (`claim_interval`).
- `app/tasks/keyword_monitor.py:503-516`, which passes `continuation` correctly already.

### Sketch diff (not applied)

```diff
--- a/app/collectors/newsfirehose_collector.py
+++ b/app/collectors/newsfirehose_collector.py
@@ search_articles params
-            if end_date is not None:
-                params["to_date"] = (end_date.strftime("%Y-%m-%d") ...)
+            if end_date is not None:
+                # The server reads to_date as midnight at the START of that day
+                # (published_at <= date), so a same-day interval searched one
+                # instant. Ask through the next day; dedup absorbs the overlap.
+                params["to_date"] = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

+    async def _search_page(self, chunk, *, page, page_size, start_date, end_date,
+                           language, sort_by) -> tuple[list, bool]:
+        """One /v1/search request. Returns (articles, has_more). Raises on
+        HTTP or network errors so collect() can classify them."""
+        ...  # body of the existing _fetch, plus data.get("has_more", False)
+
+    async def collect(self, query, topic, *, interval_start=None, interval_end=None,
+                      max_results=10, continuation=None, **kw) -> CollectionResult:
+        """Page every OR-chunk to its proven end (has_more=False). Stop at the
+        page budget with a partial result and a {chunk, page} continuation."""
+        res = self.new_result(query, interval_start, interval_end)
+        chunks = self._split_query_terms(self._normalize_query(query))
+        cont = continuation or {}
+        ci, page = int(cont.get("chunk", 0)), int(cont.get("page", 1))
+        pages, seconds = page_budget()
+        clock = PageClock(provider_max_pages("NEWSFIREHOSE_MAX_PAGES", pages), seconds)
+        seen = set()
+        try:
+            while ci < len(chunks):
+                rows, has_more = await self._search_page(
+                    chunks[ci], page=page, page_size=100,
+                    start_date=interval_start, end_date=interval_end,
+                    language=kw.get("language"), sort_by=kw.get("sort_by"))
+                clock.tick()
+                res.counts.received += len(rows)
+                for a in rows:
+                    key = a.get("url") or a.get("external_id")
+                    if key in seen:
+                        res.counts.duplicate += 1; continue
+                    seen.add(key)
+                    res.items.append(self._format_article(a, topic))
+                if has_more:
+                    page += 1
+                else:
+                    ci, page = ci + 1, 1
+                if ci < len(chunks) and clock.exhausted:
+                    out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
+                                                   continuation={"chunk": ci, "page": page})
+                    out.counts, out.started_at = res.counts, res.started_at
+                    return self.finish(out, query, interval_start, interval_end)
+        except Exception as exc:  # noqa: BLE001
+            out = CollectionResult.from_exception(exc, host=host_of(self.base_url),
+                                                  continuation={"chunk": ci, "page": page})
+            return self.finish(out, query, interval_start, interval_end)
+        return self.finish(res, query, interval_start, interval_end)
```

`search_articles()` stays as the compatibility list API for other callers. It can call `collect()` and return `result.items[:max_results]`, the way TheNewsAPI does. The existing 30-day client-side date filter should move into `collect()` unchanged.

```diff
--- a/app/collectors/contracts.py
+++ b/app/collectors/contracts.py
+TRUNC_PAGE_CAP = "page_cap"  # list-only provider; full page accepted, coverage not proven
@@
     def may_advance_checkpoint(self) -> bool:
-        return self.status == STATUS_SUCCESS and self.coverage_complete and not self.parse_partial
+        if self.status != STATUS_SUCCESS or self.parse_partial:
+            return False
+        # A list-only provider cannot page, so waiting never helps: advance,
+        # and keep coverage_complete=False in the run record as the limitation.
+        return self.coverage_complete or self.truncated_reason == TRUNC_PAGE_CAP

--- a/app/collectors/base_collector.py
+++ b/app/collectors/base_collector.py
         if max_results and len(items) >= max_results:
             res.coverage_complete = False
-            res.truncated_reason = TRUNC_PROVIDER_LIMIT
+            res.truncated_reason = TRUNC_PAGE_CAP
             res.diagnostics["note"] = "list API returned a full page; no proven end"
```

Make the same change in `xpoz_collector.py:469` (`"provider_limit"` becomes `TRUNC_PAGE_CAP`).

```diff
--- a/app/services/collection_runs.py
+++ b/app/services/collection_runs.py
+MAX_STALLED_RUNS = int(os.environ.get("CHECKPOINT_MAX_STALLED_RUNS", "6"))
@@ commit_interval, before the branches
+        stalled = (not result.may_advance_checkpoint and result.status != "partial"
+                   and cp.consecutive_failures + 1 >= MAX_STALLED_RUNS
+                   and not (result.failed and result.error_code == ERR_QUOTA))
+        if stalled:
+            logger.warning("checkpoint %s/%s stalled %d runs on %s..%s; advancing with unknown coverage",
+                           cp.provider, cp.scope_key, cp.consecutive_failures + 1,
+                           cp.interval_start, cp.interval_end)
+            # same UPDATE as the success branch, plus
+            #   coverage_unknown_before = GREATEST(coverage_unknown_before, :b)
+            #   last_error_code = 'stalled_advanced'
```

Also add a test case to `tests/test_collection_runs_db.py` for the stall rule. Then add tests to `tests/test_provider_collectors_outcomes.py`:

- 230 firehose rows across three pages give 230 items and a complete result.
- A budget stop gives `partial` with a `{chunk, page}` continuation.
- A same-day interval sends `to_date` = the next day.

### Do stuck windows need a manual reset?

**With option (a), no reset is needed.** The stuck rows keep their old interval and a NULL continuation. The next claim returns that same interval, the fixed collector pages it to `has_more=false`, and the checkpoint advances. The interval after that runs from the old `interval_end` (about 2 October) to now, capped by the 7-day lookback, so the 2–7 October gap is collected in that run, or across a few runs as partials.

Two caveats:

- **The 14 same-day scopes recover on their own.** Their frozen windows (for example 10-02 05:24 to 10-02 17:25) become a real one-day search once `to_date` is fixed, so they need no special handling.
- **A late deploy loses part of the gap.** If the fix lands more than 7 days after 2 October (after about 9 October), the lookback cap sets `coverage_unknown_before`. The part of the gap older than 7 days is then not collected. To avoid that, deploy before then, or raise `search_date_range` for one cycle.

**Option (b) or the safety valve alone also needs no reset,** because each stuck scope advances on its next run. But the gap from 2 October to now is then covered only by the top 10 per interval.

**Option (c) alone needs a reset for any scope with 100 or more hits in its frozen window.** The clean reset is this:

```sql
UPDATE collection_checkpoints
   SET coverage_through = interval_end, continuation = NULL, consecutive_failures = 0
 WHERE provider = 'newsfirehose' AND consecutive_failures > 0;
```

This skips the stale frozen window rather than re-reading it. It is a write, so I did not run it.

**The fix must also go to abm.** abm has the same code, 9 stuck firehose scopes and 5 stuck xpoz scopes for its main brands. bwtemplate is inactive and has no checkpoints. Any later copy of 6f8d4fbd to other tenants should include this fix.
