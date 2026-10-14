# Bright Data web access for Auspex — spec

Status: phase 1 built on bugfixing 14 Oct 2026 (`app/services/brightdata_web.py`, tests
`tests/test_brightdata_web.py`). Site: bugfixing.aunoo.ai only until it has run for a week. See
"As built" at the end.

## Summary

Auspex's deep research can already search the open web, but only through Google Programmable
Search, and it only ever sees the result snippets. This spec makes Bright Data's hosted MCP
server the first choice for that web search, and adds a second step that fetches the full text of
the best results. Google and TheNewsAPI stay as fallbacks in the same order as today.

We use two things from Bright Data and nothing else: search and page fetch. The paid data tools
(LinkedIn, Crunchbase, social, the remote browser) stay out of the agent's reach, because a
looping agent could run up the per-call charges in minutes.

A later phase offers the same two tools to customers through our own `/mcp` server. That phase is
designed here but not built.

## Why now

- **Snippets are too thin.** A Google result gives the agent about 160 characters per page. Deep
  research then reasons over headlines, not over what the pages say.
- **Google search is going away.** Google closed the Custom Search JSON API to new customers and
  has said existing customers lose it on 1 January 2027. Check the date before relying on it, but
  we need a replacement either way.
- **We already pay Bright Data.** `BRIGHTDATA_API_KEY` drives the Market Monitor datasets, so this
  adds a use, not a supplier.

## What exists today

| Piece | Where | What it does |
|---|---|---|
| Web search | `AuspexToolsService.google_web_search`, `app/services/auspex_tools.py:578` | Calls Google, returns `{query, total_results, articles: [{title, url, summary, source, ...}]}` |
| Routing | `SearchRouter.execute_routed_search`, `app/services/search_router.py:250` | Picks our database, the web, or both. Web means Google first, then TheNewsAPI for the last 7 days |
| Callers | `deep_research_service.py:893,1032`, `article_intelligence_analyzer.py:511`, `strategic_intelligence_service.py:536` | The only paths that reach the web today |
| Auspex chat | `AuspexService._use_mcp_tools` | Searches our own articles only. **Not changed by this spec** |
| Our MCP server | `app/mcp_access/tools.py` | Offers `google_web_search` to customers when Google is configured |
| Spend ledger | `app/services/shared_ledger.py`, `provider_quota.py` (`QuotaGuard`) | Host-wide per-provider quota counts |

The `mcp` Python package (1.26.0) is already in the venv, so we need no new dependency.

## Design

### 1. Configuration

New `.env` entries, all optional. With `BRIGHTDATA_MCP_TOKEN` unset, nothing changes.

```
BRIGHTDATA_MCP_TOKEN=...              # the token from the MCP URL; never logged
BRIGHTDATA_MCP_GROUPS=advanced_scraping   # not used by this phase: the URL names tools= instead
BRIGHTDATA_WEB_DAILY_CALLS=150        # search + fetch calls per day; see the note on the shared free pool
BRIGHTDATA_WEB_RUN_CALLS=25           # calls per research run
```

We build the server URL in code from the token and the groups. The token goes in the query
string, so every log line, exception message and stored error must pass through one `_redact()`
helper that replaces `token=...`. The test suite checks this (see Tests).

### 2. The client: `app/services/brightdata_web.py` (new)

One module, two public functions, matching the result shape `google_web_search` already returns
so that callers need no changes.

```python
async def web_search(query: str, max_results: int = 10, *, run_budget: RunBudget | None = None) -> dict
async def fetch_page(url: str, *, max_chars: int = 12000, run_budget: RunBudget | None = None) -> dict
```

- **Transport.** It uses `mcp.client.streamable_http` and opens a session per call. If that
  costs too much per call, we keep one session per event loop. A shared session must not cross
  event loops, because the monitors run off the main loop (see the Oct 10 loop-stall work).
- **Tools called.** `search_engine` (`query`, optional `engine`, `geo_location`, `cursor`) for
  search and `scrape_as_markdown` (`url`) for fetch. Both names and inputs are confirmed from the
  server's tool list, saved in `docs/brightdata_mcp_tools.json` on 13 Oct 2026.
- **Allowlist: exactly those two names.** The module refuses any other tool name. This matters
  more than the dashboard suggests. The live server has no per-site data tools any more. Instead,
  even the base set with no `groups` includes `run_scraper`, which runs any of Bright Data's 1,200+
  paid scrapers and bills every record it returns. Bright Data's docs confirm the scraper tools
  are on by default.
- **Server-side allowlist as well.** The server accepts a `tools=` parameter that limits the
  session to named tools (Bright Data docs, 13 Oct 2026). We build the URL with
  `tools=search_engine,scrape_as_markdown` and no `groups`, so the server never offers
  `run_scraper` to this client. The allowlist in our code stays as a second check, in case the
  server ignores the parameter.
- **Timeouts.** Search gets 20 s and fetch gets 40 s. A timeout returns
  `{"error": ..., "articles": []}`, the same shape Google's errors take, so the router's fallback
  logic keeps working.
- **Budget.** Before every call it checks two limits: the site's daily count through the shared
  ledger (`QuotaGuard`, provider key `brightdata_web`) and the optional per-run `RunBudget`. If
  either limit is spent, it returns an error result and does not make the call.

### 3. Search routing

`execute_routed_search` gains one provider ahead of Google, in both the external and the hybrid
branches:

1. Bright Data `web_search`, when the token is set and the budget allows.
2. Google, when configured.
3. TheNewsAPI, last 7 days.

`results["metadata"]["search_method"]` records which one answered (`brightdata`, `google_pse`
or `thenewsapi`), so we can see the mix in logs. The rest of the router is unchanged.

### 4. Full-text fetch in deep research

After deep research ranks the external results, it fetches the top 3 per sub-question with
`fetch_page` and puts the page text in place of the snippet.

- **Fetched pages are untrusted.** A page can carry text written to steer the model, and this is
  the same risk the retrieval-poisoning work dealt with for our own articles. The fetched text
  goes into the prompt inside a delimited block labelled as quoted web content, never as an
  instruction. We cut it to `max_chars`, strip scripts and hidden markup, and drop it if it
  contains none of the query's terms.
- **We store nothing.** Fetched pages are not written to `articles`. They would skip the relevance
  check and the AI analysis step, and the readable-articles rules assume every row went through
  both. The research report cites the URL, as it does for Google results now.
- **We fetch each page once per run.** A URL fetched earlier in the same research run comes from a
  per-run dictionary.

### 5. Tool-list snapshot script: `scripts/brightdata_mcp_tools.py` (new)

This script asks the server for its tool list, which costs nothing, and writes it to
`docs/brightdata_mcp_tools.json` with the token removed. It takes `--groups` so we can list the
paid groups too without calling any of them.

A first snapshot was taken by hand on 13 Oct 2026 and is in `docs/brightdata_mcp_tools.json`
(30 tools with every group on, 11 with none).

This also helps the Market Monitor, through `get_scraper_details`. Given a dataset ID and a
method, it returns the scraper's input fields, a sample input and its main output fields. That is
the sample request we have been asking for by hand before wiring any dataset, plus the output
fields we never had. It should settle the unverified Crunchbase discovery input, the Indeed
`posted_by` field and the PitchBook and Indeed output mappers in `brightdata_linkedin.py`. It
probably counts against the 5,000 free calls but runs no scraper. `run_scraper` stays off-limits
for this.

### 5a. `discover`, a candidate for later

With `advanced_scraping` on, the server also offers `discover`: a web search that ranks results
by relevance to a stated intent and filters by date (`start_date`, `end_date`), country and
keywords. Date filtering is something `search_engine` lacks and deep research wants. Its price is
not on the dashboard, so phase 1 leaves it out of the allowlist. Add it once we know the price.

### 6. Customer MCP tools (phase 2, not built now)

Later, `/mcp` offers `web_search` and `fetch_page` to customers, backed by the client above:

- Each MCP key gets a daily call limit, counted from `mcp_tool_calls`, plus the site's daily limit.
- The tools are listed only when the token is set, the same way `needs_google` gates
  `google_web_search` today.
- Paid groups are never offered through `/mcp`.
- **Blocker:** before building, we confirm that Bright Data's terms allow results from our account
  to reach our customers' agents. I haven't checked the terms.

## Out of scope

- Auspex chat. It stays on our own articles. Adding the web there is a separate decision about what
  chat answers should be grounded in.
- The paid groups (`business`, `social`, `browser`, `ecommerce`, `finance`, `research`,
  `app_stores`) for any agent path.
- Moving the Market Monitor's dataset calls onto MCP. They work, and they run on batched triggers
  that MCP doesn't offer.
- Any site other than bugfixing.

## Tests

In `tests/test_brightdata_web.py`, with the MCP session mocked so nothing reaches Bright Data:

1. Search returns the `google_web_search` result shape.
2. A tool name outside the allowlist is refused without a network call.
3. A spent daily limit or run limit returns an error result and makes no call.
4. Timeout and server error both return `{"error", "articles": []}`.
5. **The token never appears** in log output, raised exceptions or returned errors (capture logs,
   force each error path, search for the token string).
6. The router falls back Bright Data → Google → TheNewsAPI, and `search_method` names the one that
   answered.
7. Fetched text is wrapped in its quoted block, cut to length, and dropped when it has no query
   terms.
8. A URL fetched twice in one run makes one call.

The existing suite must stay green (baseline 2,267 passed, 0 failed on 11 Oct 2026).

## Rollout

1. Done 13 Oct 2026: `BRIGHTDATA_MCP_TOKEN` and `BRIGHTDATA_MCP_GROUPS=advanced_scraping` are in
   bugfixing's `.env` (backup `.env.bak-brightdata-mcp-20261013`). It is a different key from
   `BRIGHTDATA_API_KEY`.
2. Done 13 Oct 2026: the tool list confirms `search_engine` and `scrape_as_markdown` and their
   inputs. The token accepts every group.
3. Build, test, restart bugfixing when no jobs are running.
4. Run three deep-research questions by hand. Compare them with the same questions on Google
   snippets, and read the spend for the day in the Bright Data dashboard.
5. After a week, check the call counts in the ledger against the dashboard bill before offering
   it to any other site.

## Open questions

- **The free 5,000 is one pool for the whole account.** Bright Data's docs say the MCP free tier
  is the account's Web Unlocker allowance, shared by every user and every use on the account. So
  the daily limit is per account, not per site: with two sites on this key, each gets 75. The
  shared host ledger (`shared_ledger.py`) can count across sites, so the limit should be set there,
  keyed on the account.
- **Price after the free allowance.** The dashboard (13 Oct 2026) shows the seven search and
  fetch tools include 5,000 calls a month free, but not what a call costs beyond that. The daily
  limit of 150 keeps one site inside the free allowance (150 × 30 = 4,500). The allowance is per
  account, not per site, so a second site on the same key needs the limit split.
- **Whether the per-record price replaces the dataset minimum.** The dashboard lists the data tools
  at $2.50 per 1,000 records (browser: $8.40 per GB) and names no minimum per call. Our dataset
  triggers do carry a minimum per call. If the MCP data tools really bill per record only, a single
  LinkedIn or Crunchbase lookup costs a quarter of a cent, which matters for the Market Monitor's
  one-vendor "Fetch now". Confirm with Bright Data or from one bill before acting on it.
- **Bright Data's terms for phase 2**, as above.
- **`search_engine` ignored `site:` in one test** (13 Oct 2026: `Oviva app site:play.google.com`
  returned unrelated apps). A Reuters search built on `site:reuters.com` must therefore filter the
  results by domain in our code, and it may come back thin.

## Effort (AI time)

About 3 to 4 hours for phase 1: the client and snapshot script take about 1 hour, the router and
deep-research changes 1 to 1.5 hours, and tests and the bugfixing rollout the rest. Phase 2 is
about 1.5 hours more once the terms question is answered.

## As built (14 Oct 2026)

- **Google search was already off on bugfixing.** Google answered every request with 403
  `API_KEY_SERVICE_BLOCKED`, so before this change deep research's web searches all fell through
  to TheNewsAPI's last 7 days. Bright Data is now the only working web search on the site.
- **Bright Data search is slow and uneven.** Measured live on 14 Oct 2026:
  - "Oviva GLP-1" took 31 s and returned 9 good results.
  - "Oviva weight loss" took 48 s and returned none.
  - "Oviva GLP-1 weight loss programme UK" took 64 s with no location set, and 55 s with
    `geo_location: gb`. Both returned none.
  - The `bing` engine answered in 6–12 s, but as a Markdown page in Traditional Chinese with every
    link behind a Bing redirect. We don't parse it.

  So the search timeout is 45 s (`BRIGHTDATA_WEB_SEARCH_TIMEOUT`). A search that times out or
  comes back empty falls through to Google and then TheNewsAPI, as designed.
- **Page fetch is fast and clean:** 5–7 s per page, with the page's own text.
- **Budgets.** The daily budget is in the host's `quota_policy.json`:
  `"brightdata_web": {"period": "day", "budget": 150}`, counted per token across every site
  (backup `quota_policy.json.bak-brightdata-web-20261014`). Without that entry,
  `BRIGHTDATA_WEB_DAILY_CALLS` applies. The per-run budget lives on the research state
  (`state.web_budget`). Each search and fetch sets it only around its own `await`, because
  `conduct_research` is an async generator, and a context variable set across its `yield`s is
  not safe.
- **The routing change** is a new `AuspexToolsService.web_search()`, which tries Bright Data and
  then Google. `search_router` calls it in both the external and the hybrid branches.
  `metadata.search_method` (or `web_search_method` in hybrid) names the provider that answered.
- **Fetched text in synthesis.** Fetched pages are added to the synthesis batch as
  `web_page_text`, inside a `<<<QUOTED WEB PAGE … >>>END QUOTED WEB PAGE` block of at most 2,500
  characters. The page's own text can't close the block early.
- **Refinement-stage web results aren't fetched.** Only the planner queries' results are, after
  sampling, three per query.
