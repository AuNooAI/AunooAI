# Market Monitor on the monolith

Built: 2026-08-19. Tree: `/home/orochford/tenants/bugfixing.aunoo.ai`.
Migration `mm_001` applied to the `test` database. 31 tests pass; the existing
suite is unchanged (128 failures and 31 errors before and after, all
pre-existing).

The feature also exists in the SaaS codebase under `saasmvp-app/`, where it was
built first — the supplied specification was written against that architecture.
See `saasmvp-app/docs/MARKET_MONITOR_SPEC_REVIEW.md` for the spec review, the
defects found in it, and the SaaS build. The two are separate implementations
of the same design and will diverge; per the standing rule, SaaS features do not
propagate to monolith tenants.

## What a market is

A portfolio of `bw_brands` plus the question and ontology that make them
comparable. The first is SOC Automation: 83 vendors from an IT-Harvest registry,
82 of them in scope.

## Files

| Piece | Where |
|---|---|
| 8 tables | `alembic/versions/mm_001_market_monitor.py` |
| Workbook parser, validation report, transactional commit | `app/services/market_import.py` |
| Articles, snapshots, run lifecycle, attribution | `app/services/market_collect.py` |
| Bright Data LinkedIn dataset client | `app/services/brightdata_linkedin.py` |
| Feed/page discovery, conditional fetch, semantic diff | `app/collectors/vendor_web_collector.py` |
| 12/24-hour collection loop | `app/tasks/market_monitor.py` |
| API and the provider callback | `app/routes/market_monitor_routes.py` |
| Module registration | `app/core/modules.py` |
| Tests | `tests/test_market_import.py`, `tests/test_market_collection.py` |

## How it differs from the SaaS build

- **No tenant column and no RLS.** A monolith deployment is one customer. A
  tenant column here would always hold the same value and a policy would never
  exclude anything.
- **No entitlement.** `max_market_entities` exists in the SaaS build because an
  82-vendor market blows past a plan's brand cap. There are no plans here.
- **`article_uris TEXT[]`, not integer ids.** `articles` is keyed on `uri`,
  which is also why `bw_article_categories` carries `article_uri`.
- **Vendors get no monitoring topic, and nothing needed excluding from the
  collector.** Brand Watcher classifies the shared article corpus by brand
  keywords, and collection is driven by `keyword_groups`. In the SaaS build,
  giving 82 vendors a topic each would have multiplied the platform-wide
  15-minute collection cycle 5.8x for every tenant, which needed an explicit
  exclusion. That problem does not exist here.
- **No Redis leader lock.** One process, so the loop cannot race itself.
- **Articles are written directly**, following `bw_official_sources`, rather
  than through a collector pipeline.

## Turning it on

1. Enable the **Market Monitor** module from the Explore gear icon. Until then
   its routes 404 and its loop never starts — `module_config` has no row for it,
   which is deliberate and fail-closed.
2. Set `MARKET_MONITORING_ENABLED=true`. The loop is a no-op without it.
3. For LinkedIn collection, set `BRIGHTDATA_LINKEDIN_ENABLED=true`,
   `BRIGHTDATA_LINKEDIN_WEBHOOK_SECRET`, and a Bright Data key — either
   `BRIGHTDATA_LINKEDIN_API_KEY` or the shared `BRIGHTDATA_API_KEY`. Website and
   feed monitoring need none of this.
4. Optional: `MARKET_POLL_INTERVAL_HOURS` (12), `MARKET_SLOW_POLL_INTERVAL_HOURS`
   (24), `MARKET_MAX_VENDORS_PER_RUN` (20), `MARKET_MONTHLY_BUDGET_USD` (0 = no
   cap), `BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID`,
   `BRIGHTDATA_LINKEDIN_POSTS_DATASET_ID`.
5. `APP_URL` must be the public origin, or the Bright Data callback URL points
   nowhere and every async batch is paid for and lost.

## Importing a registry

`POST /api/market-monitor/markets` to create the market, then
`POST /api/market-monitor/markets/import/validate` with the workbook. The report
lists every vendor, every alias inferred, every alias refused, and every review
task, keyed by a `batch_id` derived from the file's bytes. `import/commit` takes
the same file and that `batch_id` back — re-deriving it proves the operator is
committing the registry they reviewed — and writes in one transaction.

Verified against the real workbook, in a rolled-back transaction: 83 brands
created alongside the 2 existing ones, 82 active, 1 excluded, 83 websites, 81
LinkedIn URLs, 3 aliases, 83 baseline snapshots, 28 review tasks. 39 vendors
carry disclosed funding; 44 have none and none was written as zero. A second run
of the same file changed no counts.

## Vendor toggles

Three flags on `bw_market_brands`, because they are three decisions: `role` is
what the row is, `collection_enabled` is whether we spend anything watching it,
`is_public` is whether it reaches a public surface.

`POST /api/market-monitor/markets/{id}/vendors/collection` takes a rule over the
imported baseline — funding status, country, category, sub-category, headcount
range, founding year, funding amount, whether a LinkedIn page exists — or an
explicit id list. "Only collect for funded vendors" is
`{"filter": {"funding_status": ["Disclosed"]}, "enabled": true, "dry_run": false}`,
which selects 39. It defaults to a dry run and returns exactly which vendors
would change; an empty rule is refused rather than read as "all 82".
`GET .../vendors/facets` returns the values this registry actually contains, so
the UI builds its options from the data.

A rule that names no role never reaches an excluded vendor. Scope and funding
are different questions, and Edge Delta is both funded and out of scope — the
first live run of "collect for every funded vendor" would have switched it on.
Ask for excluded rows by naming `roles` explicitly.

## Three rules the workbook forced

- **A parenthetical is only a former name when it says so.** `Variance (was
  Intrinsic)` yields the alias "Intrinsic". `Strike48 (A Devo company)` is an
  ownership statement and yields a review task, not an alias called "A Devo
  company".
- **An empty funding cell is data.** 44 of 83 rows are Undisclosed or
  Bootstrapped and carry no amount. Writing 0 would turn "we don't know" into
  "they raised nothing".
- **Two vendors on one LinkedIn page is a merge nobody made yet.** Crogl and
  System Two Security both point at `linkedin.com/company/system-two-security`.
  The partial unique index would have swallowed the second insert in silence and
  given every post from that page to one vendor. The importer assigns the
  identifier to the earlier row and files a high-severity review task naming
  both — the same shape as the Cyber Triage / Sleuth Kit Labs merge the
  workbook's own Changes tab records.

## Not verified

No live Bright Data call was made. The dataset ids, the exact record field names
and the callback's real body shape are unconfirmed. The mappers read several
plausible field names rather than pinning one, and the callback accepts both a
bare record array and a `{data: [...]}` envelope, but the first real batch needs
watching.

There is no UI yet. Everything above is API-only.

## Live state

Enabled and imported on 2026-08-19. Module `market_monitor` is on in
`module_config`; market id 2, slug `soc-automation`, 82 active vendors and 1
excluded, alongside the pre-existing Wiley and Elsevier brands. 39 vendors carry
disclosed funding, 42 undisclosed, 2 bootstrapped. 28 review tasks, one of them
high severity (the Crogl / System Two Security shared LinkedIn page). Two active
vendors have no LinkedIn URL.

`MARKET_MONITORING_ENABLED` is **not** set, so the loop starts and does nothing.
Turning it on begins fetching 82 vendors' public websites on a twelve-hour
cadence — bandwidth only, no provider spend, and capped at
`MARKET_MAX_VENDORS_PER_RUN` per run.

To undo the import: `DELETE FROM bw_markets WHERE slug = 'soc-automation'`
cascades the membership, snapshot, run and review-task rows. The 83 `bw_brands`
rows survive by design — the delete route does not cascade into them because
that would destroy monitoring configuration and article attribution. Remove them
with `DELETE FROM bw_brands WHERE display_name NOT IN ('Wiley','Elsevier')`,
after checking nothing else has attached to them.
