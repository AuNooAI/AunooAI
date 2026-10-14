# App store reviews as a Brand Watcher source — spec

Status: built on bugfixing 14 Oct 2026, not yet on oviva. First customer site: oviva.aunoo.ai.
Code: `app/services/bw_app_reviews.py`, wired in through `bw_official_sources.py`; migration
`bw_app_001`; tests `tests/test_bw_app_reviews.py`. See "As built" at the end for where the
build differs from the design below.

## Summary

Brand Watcher will collect a brand's Google Play and Apple App Store reviews every day, through
Bright Data's review scrapers. Each new review lands as a post on the brand's page, the same way
Glassdoor reviews land today. Once a day we also save the app's overall rating, review count and
downloads, so the brand gets a rating trend and an alert when the rating drops.

Oviva is the first brand to get it, because its product is an app. Any brand on the site can turn
it on by adding its app IDs, which covers Oviva's competitors once we know the cost.

## Why

- **Oviva has almost no earned press.** In the 90 days to 1 Oct 2026 it had 19 press items.
  Its app has 30,673 Google Play reviews. Those reviews are the largest body of customer opinion
  about Oviva, and Brand Watcher sees none of it today.
- **The reviews are specific and actionable.** The five we fetched in the test call on 13 Oct
  2026 complained about patronising lesson content, too many notifications, unanswered chat
  messages, and AI nutrition labels that marked chicken nuggets and chips as a balanced meal.
- **They show service failures that press never covers.** "No one replies to chat messages" is a
  care-quality signal for a clinical service.

## What the test call established

One paid call on 13 Oct 2026, snapshot `sd_mv72982jnx6gz1cnh`. The full notes are in
`BRIGHTDATA_BRAND_MARKET_SOURCES.md`.

- Google Play dataset `gd_m6zagkt024uwvvwuyu` returned 5 reviews in about 4 seconds, with no
  errors.
- Without `language`, reviews come back in English even for `country: "DE"`.
- Reviews are **not** returned newest first, so we must pass `start_date`.
- `app_developer` is wrong ("Google Commerce Ltd"). We don't store it.
- The Apple App Store dataset `gd_m734msue16e0adkbit` has not been called yet. It takes only an
  app URL, with no date or count input, so we don't know how many reviews one call returns.

## Oviva's apps

| Store | App | ID | Found by |
|---|---|---|---|
| Google Play | Oviva (main app) | `com.rementr` | Test call; 30,673 reviews, 413,668 downloads, rating 4.41 |
| Google Play | Oviva Direkt (German DiGA app) | `com.rementr.diga` | Search result, not yet checked |
| App Store | Oviva Direkt (Germany) | `id1556652646` | Search result, `apps.apple.com/de/...` |
| App Store | Oviva (UK) | unknown | To find. The Oviva site is about the UK GLP-1 programme, so this is the one that matters most |

Before go-live, an operator confirms each ID against the store page. Search found these, and
search can be wrong.

## Design

### 1. Configuration, per brand

These go in `bw_brands.config`, next to the existing `glassdoor_company_id`:

```json
{
  "extra_sources": ["google_play", "app_store"],
  "app_store_targets": [
    {"store": "google_play", "app_id": "com.rementr",       "country": "GB", "language": "en"},
    {"store": "google_play", "app_id": "com.rementr.diga",  "country": "DE", "language": "de"},
    {"store": "app_store",   "app_id": "1556652646",        "country": "de"},
    {"store": "app_store",   "app_id": "<UK id>",           "country": "gb"}
  ]
}
```

Each target is one app in one country store. We build the store URL in code from the ID and the
country, so nobody pastes URLs by hand.

### 2. Two new official sources in `app/services/bw_official_sources.py`

Brand Watcher's "official sources" already do what we need. Each is opt-in per brand through
`extra_sources`, polled at most once every 24 hours per brand through the
`config.source_state` cursor, landed as `articles` rows, and attributed to the brand in
`bw_article_categories`. Glassdoor runs this way today.

We add two entries to `OFFICIAL_SOURCES`:

| Key | Label | `news_source` | Category | Term gate | Factuality / credibility |
|---|---|---|---|---|---|
| `google_play` | Google Play reviews | `Google Play` | Brand Sentiment & Perception | off | mixed / medium |
| `app_store` | App Store reviews | `App Store` | Brand Sentiment & Perception | off | mixed / medium |

Both have `requires_key: "BRIGHTDATA_API_KEY"`. The term gate is off for the same reason it is off
for Glassdoor: the app ID already ties a review to the brand, and reviews rarely name the brand.

Today's fetchers take `(term, since)`. The new ones need the brand's targets, so
`poll_official_sources` passes the brand config to fetchers that ask for it. The five existing
fetchers don't change.

### 3. Fetching

The scheduled job calls the Bright Data REST API we already use, through
`LinkedInDatasetClient.scrape_sync` in `app/services/brightdata_linkedin.py`, with the site's
`BRIGHTDATA_API_KEY`. It does not go through MCP. We used MCP to find and test the datasets, but
MCP is built for agents, and the REST path already has our error handling and retries.

- **Google Play:** one sync scrape per target, with `url`, `country`, `language`,
  `start_date` set to the cursor date, and `num_of_reviews` capped at 50.
- **App Store:** one sync scrape per target, with only `url`. We keep the reviews dated after
  the cursor and drop the rest. The first paid call must be a single app in a single country, so
  we can see how many reviews one call returns and what it costs.
- **First run:** the existing `INITIAL_LOOKBACK` of 30 days applies.
- **Errors:** a target that fails is logged and skipped, and the other targets still run. The
  cursor moves forward only when every target for that brand succeeded, so a failed day is
  fetched again the next day.

### 4. What we store for each review

Each review becomes one `articles` row through the existing `_land_and_attribute`.

| Field | Value |
|---|---|
| `uri` | Google Play: `https://play.google.com/store/apps/details?id=<app_id>&reviewId=<review_id>`. App Store: `https://apps.apple.com/<cc>/app/id<app_id>#review-<review_id>`. Both are unique and stable, so a review fetched twice lands once |
| `title` | `Google Play review (2/5): <first 80 characters>` |
| `summary` | The review text, then `Oviva replied: …` when the store gives a developer reply (App Store only) |
| `publication_date` | `review_date` |
| `sentiment` | From stars, as for Glassdoor: 4–5 Positive, 3 Neutral, 1–2 Negative |
| `author` | Empty. See privacy below |
| `social_meta` | `store`, `app_id`, `country`, `rating`, `found_helpful`, `app_version` where given, `has_developer_reply` |

**We don't store reviewer names.** Health app reviews often describe the writer's own conditions,
as in the test call ("I'm severely disabled and have multiple health conditions"). The review text
is public and the brand needs it, but storing it next to a name builds a list of named people
with their health details, which we have no reason to hold.

**Translation.** German reviews are translated to English when they land, with the original kept,
using the same helper as the Market Monitor (`english_fields` in
`app/utils/title_translation.py`, as `market_collect._translate_landed` uses it).

**Who wrote it.** The voices view marks every Glassdoor post as `employee`
(`brand_watcher_routes.py:1584`). In the same place we mark App Store and Google Play reviews as
`patient` for brands whose sector is health, and `customer` for every other brand.

**Risk check.** Landed reviews already go through `_risk_pass`, which flags adverse-risk wording.
For a GLP-1 programme, that will catch reviews that mention side effects. See the open question
on pharmacovigilance.

### 5. The daily rating record

Every Google Play response repeats the app's own figures (`app_rating`, `app_number_of_reviews`,
`app_downloads`). Once a day per target we save one row to a new table:

```
bw_app_snapshots
  id              serial primary key
  brand_id        integer not null references bw_brands(id)
  store           text not null            -- google_play | app_store
  app_id          text not null
  country         text not null
  snapshot_date   date not null
  rating          numeric(3,2)
  review_count    integer
  downloads       integer                  -- Google Play only
  data            jsonb                    -- the raw app-level fields
  unique (brand_id, store, app_id, country, snapshot_date)
```

The table is created by an Alembic migration, `bw_app_001`. On oviva its `down_revision` is that
site's current head, `ts_011`. On bugfixing it follows bugfixing's own head.

The App Store scraper returns no app-level rating. Its row stores only what we can count
ourselves: reviews fetched and the share with a developer reply.

A Google Play call that returns no new reviews returns no rows, and so no app figures. On those
days the snapshot is skipped. That's acceptable for a trend, and it costs nothing.

### 6. Alerts

There are two new rules in `brand_watcher_monitor.py`, next to `glassdoor_deterioration`:

- **`app_rating_drop`:** the rating in `bw_app_snapshots` fell by at least 0.1 within 35 days,
  with the two readings at least 7 days apart. A 0.1 fall on 30,000 reviews takes a large wave of
  bad reviews, so it's a real event.
- **`app_negative_spike`:** 1–2 star reviews in the last 7 days are at least double the weekly
  average of the previous 8 weeks, and there are at least 5 of them. This catches a bad app
  release within days, long before it moves the overall rating.

Both rules are on by default, can be tuned per brand like the other rules, and use the existing
alert identity, so a repeat isn't sent twice.

### 7. Spending limit

These sources aren't tied to a market, so the Market Monitor's monthly budget, which sums
`bw_collection_runs` by market, doesn't see them. Each call instead counts its records in the
shared host ledger (`app/services/shared_ledger.py`, provider key `brightdata_app_reviews`).
Calls stop for the month once the site passes `BW_APP_REVIEWS_MONTHLY_RECORDS`, which defaults
to 4,000 records, about $10.

For Oviva alone the cost should be far lower. Assume the four targets get up to 20 new reviews
a day between them. That is 600 records a month, about $1.50 at $2.50 per 1,000, plus whatever
minimum per call applies (see open questions).

### 8. UI

There's no new page:

- Reviews appear in the brand's existing posts and voices views, because they are ordinary brand
  posts with `news_source` set to the store.
- The two sources appear in the existing "extra sources" settings list automatically, because
  that list is built from `OFFICIAL_SOURCES`.
- **One addition:** a small "App ratings" card on the brand page. It shows each target's
  current rating, its change over 30 days, and the review count, read from `bw_app_snapshots`.
  It needs a React change and a UI build.

## Out of scope

- Replying to reviews. We read them only.
- Amazon, Trustpilot and G2 reviews. They are separate specs, though they will reuse this
  design.
- Any site other than oviva. Bugfixing gets the code for testing but no customer brand config.
- Competitor apps. The design supports them. We switch them on after a month of Oviva cost
  data, if Oviva asks.

## Tests

In `tests/test_bw_app_reviews.py`, with the Bright Data client mocked:

1. A Google Play record maps to the article fields above: the URI format, the title with stars,
   sentiment from stars, and no reviewer name anywhere in the row.
2. An App Store developer reply is added to the summary, and `has_developer_reply` is set.
3. The same review fetched twice lands once.
4. App Store reviews older than the cursor are dropped.
5. One failed target doesn't stop the others, and the cursor doesn't move.
6. The snapshot row is written once per target per day, and skipped when the call returns no
   rows.
7. `app_rating_drop` fires on a 0.1 fall across 7+ days, and stays quiet on the same fall within
   3 days.
8. `app_negative_spike` fires on 6 one-star reviews against a weekly average of 2, and stays
   quiet on 4.
9. Calls stop once the month's records pass the limit.
10. The voices view marks these reviews `patient` for a health brand and `customer` for others.

The full suite must stay green.

## Rollout

1. Build and test on bugfixing. Commit there, in the canonical tree.
2. Confirm Oviva's app IDs with an operator, and find the UK App Store ID.
3. **First App Store call by hand.** Run one call for the UK app only. Record how many reviews it
   returns and the charge on the Bright Data usage page.
4. Copy to oviva. Oviva's `bw_official_sources.py` differs from bugfixing's by 11 lines (the
   scholarly category name), so apply the change as a patch and check that it imports and runs.
   Copying the whole file would bring the category change with it. Run migration `bw_app_001`
   before restarting.
5. Set Oviva's brand config and run the poll once at once, not on the schedule, as with any site
   being set up.
6. Check the first landed reviews on the brand page and the first snapshot rows.
7. After 30 days, compare the ledger's record count with the Bright Data bill. Then offer
   competitor apps to Oviva.

## Open questions

- **Is there a minimum charge per call?** The test call's charge for snapshot
  `sd_mv72982jnx6gz1cnh` on the Bright Data usage page answers this. If there is a minimum,
  daily calls for four targets may cost more than the reviews do, and we would poll weekly
  instead.
- **Which Bright Data account pays?** Oviva's `.env` has its own `BRIGHTDATA_API_KEY`. The MCP
  test used a different key. Both need to belong to the account whose bill we watch.
- **Pharmacovigilance.** Oviva prescribes GLP-1 medication. A public review that describes a side
  effect may count as an adverse-event report Oviva has to act on once it knows about it. Our risk
  check will flag these reviews. **Oviva must decide** whether those flags should go to its safety
  team, because that changes what Oviva is obliged to do. We should raise it with Oviva before go-live.
- **Which Google Play country to read for the main app.** The test asked for Germany and got
  English reviews, which may be UK users. We pick the countries with Oviva.

## Effort (AI time)

About 3 to 4 hours:
- fetchers, landing, config and snapshot table, about 1.5 hours
- alert rules, about 45 minutes
- the ratings card and UI build, about 45 minutes
- tests and the oviva copy, the rest

The hand-run App Store call and confirming the app IDs are separate from this, and wait on you.

## As built (14 Oct 2026)

Where the build differs from the design above:

- **Spending limit.** The shared host ledger counts requests per key across all sites, but this
  limit counts records per site. So each call is logged in a new site table,
  `bw_app_review_calls` (records returned, success, error), and the limit is the sum for the
  current month. The same table is what we compare with the Bright Data bill. Before each call,
  the check assumes the most the call could return: 50 for Google Play, and 100 for the App Store
  until we have measured a real call (`APP_STORE_ASSUMED_RECORDS`).
- **Who wrote it.** No brand record says which sector a brand is in, so the role is set per brand:
  `config.app_review_author_role`, default `customer`. Oviva's config sets `patient`. The role is
  written on the article when it lands.
- **Channel.** `social_sources.classify_source` maps `Google Play` and `App Store` to the
  `community` channel, which puts reviews in the voices view, not in press coverage. The perception
  breakdown counts them as their own `app_reviews` dimension. The UI doesn't show that
  dimension yet.
- **`start_date` format.** Bright Data documents the type only as "date". We send `YYYY-MM-DD`,
  and our code also drops reviews older than the cursor, so a format it ignores costs at most the
  50-review cap per call and never lands old reviews.
- **The ratings card** is on the brand dashboard, under the summary cards. It shows only when the
  brand has snapshots.
