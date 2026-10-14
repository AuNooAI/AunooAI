# Bright Data sources for Brand Watcher and the Market Monitor

Status: options, 13 Oct 2026. Nothing here is built. Companion to `BRIGHTDATA_WEB_ACCESS_SPEC.md`.

## How this list was made

We searched Bright Data's scraper catalog through its MCP server on 13 Oct 2026, using only the
two lookup tools, `search_scrapers` and `get_scraper_details`. Neither runs a scraper, so none of
this cost a record. The dataset IDs below come from those answers, not from memory.

The dashboard price for these scrapers is $2.50 per 1,000 records, so a quarter of a cent per
review or post. Our older dataset triggers charge a minimum per call, and we have not yet
confirmed whether calls made through MCP do too.

Almost every useful scraper here is **collect by URL**. It needs the brand's or vendor's own page
on that site (its G2 product page, its Trustpilot page). So each source needs a one-off step to find
and store that URL. That step can use the free `search_engine` tool (for example
`site:g2.com/products "Dropzone AI"`), with an operator confirming the match, much as PitchBook
URLs are stored today through `PUT /markets/{id}/vendors/{brand_id}/identifier`.

## What we already have, so it's left out

- **X, Reddit, Instagram, TikTok:** Xpoz.
- **Bluesky:** our own collector.
- **LinkedIn company profile, posts and jobs, Crunchbase, PitchBook, ZoomInfo, Indeed:** existing
  Bright Data datasets in `brightdata_linkedin.py`.
- **Job listings from Greenhouse, Lever, Ashby and similar:** `ats_collector.py`.
- **Glassdoor ratings and reviews for Brand Watcher:** OpenWebNinja, in `bw_official_sources.py`.

## Market Monitor (B2B software vendors)

| Rank | Source | Dataset | Methods | What it adds |
|---|---|---|---|---|
| 1 | **G2 product reviews** | `gd_l88xvdka1uao86xvlb` | by URL; inputs `url`, `pages`, `sort_filter`, `start_date` | What buyers say about each vendor. Each review carries the reviewer's job title and company size, which shows who is actually buying. `start_date` lets each run fetch only new reviews |
| 2 | **TrustRadius product reviews** | `gd_lztojazw1389985ops` | by URL, discover by URL | A second B2B review site. Some security vendors are reviewed here and not on G2 |
| 3 | **Owler company information** | `gd_l1vilaxi10wutoage7` | by URL | Revenue and headcount estimates and a competitor list. The estimates are rough, so they would need a label saying so |
| 4 | **Glassdoor company overview** | `gd_l7j0bx501ockwldaqf` | by URL, **by keyword**, by filter | Employee rating and headcount band. The keyword method avoids the URL-finding step. Small vendors often have few or no reviews |
| 5 | **GitHub repository** | `gd_lyrexgxc24b3d4imjt` | by URL, by search URL | Stars and commit activity for vendors with open-source projects. Few vendors in the SOC market have them |

Not in the catalog: Gartner Peer Insights, Capterra, SimilarWeb, BuiltWith, Product Hunt.

## Brand Watcher (consumer and health brands)

| Rank | Source | Dataset | Methods | What it adds |
|---|---|---|---|---|
| 1 | **Apple App Store reviews** | `gd_m734msue16e0adkbit` | by URL | Reviews of a brand's app. Directly useful for Oviva, whose product is an app |
| 1 | **Google Play reviews** | `gd_m6zagkt024uwvvwuyu` | by URL | The Android side of the same reviews |
| 2 | **Trustpilot reviews** | `gd_lm5zmhwd2sni130p` | by URL; inputs `url`, `date_posted`, `num_of_reviews_limit`, `most_recent` | Customer reviews with rating and date, plus `review_replies`, so we can see whether and how the brand answers complaints |
| 3 | **YouTube videos** | `gd_lk56epmy2i5g7lzu0k` | by URL, **by keyword**, by hashtag, by filters | Videos that mention the brand. Xpoz does not cover YouTube, and the keyword method needs no URL step |
| 3 | **YouTube comments** | `gd_lk9q0ew71spt1mxywf` | by URL | Reaction under the videos found above, or under the brand's own videos |
| 4 | **Facebook page posts** and **comments** | `gd_lkaxegm826bjpoo9m5`, `gd_lkay758p1eanlolqw8` | by URL only | The brand's own page and how people react to it. Xpoz does not cover Facebook. Without a keyword method it cannot find mentions elsewhere on Facebook |
| 5 | **Google Maps reviews** | `gd_luzfs1dn2oa0teb81` | by URL | Reviews of physical sites, such as clinics or stores. Only useful for brands with locations |
| — | Glassdoor reviews | `gd_l7j1po0921hbu0ri1z` | by URL; `days` required | Only worth it if OpenWebNinja gets worse or dearer. It would replace that feed, not add to it |
| — | Quora, Yelp | `gd_lvz1rbj81afv3m6n5y`, `gd_lgzhlu9323u3k24jkv` | by URL / search URL | Niche. Yelp only for local consumer brands |

## Requested next (13 Oct 2026): details checked

Inputs and outputs below come from `get_scraper_details`. No scraper was run.

### Amazon product reviews, for consumer brands (a headset-maker prospect)

This takes two steps, because reviews are fetched one product at a time.

1. **Find the brand's products.** `Amazon products` (`gd_l7q7dkf244hwjntr0`) can discover
   products by keyword, category or best-seller list. `Amazon products global dataset`
   (`gd_lwhideng15g8jg63s7`) discovers by brand or seller, but its brand input is an Amazon
   store-search URL, not a plain brand name. Either way an operator confirms the product list,
   because a keyword like the brand name also finds accessories and look-alikes.
2. **Fetch reviews per product.** `Amazon Reviews` (`gd_le8e811kzy4ggddlq`) takes the product URL,
   `max_reviews`, `variation_specific`, and `reviews_to_not_include`. That last input takes the
   review IDs we already hold, so each run fetches only new reviews. That makes it cheap to run
   on a schedule. The output includes star rating, text, date, country, verified purchase, Vine
   reviewer, helpful votes and product variant, plus the product's overall rating and count.

Rough cost: 40 products × 20 new reviews a week = 800 records, about $2 a week. The first full
pull is larger and should be capped with `max_reviews`.

### App Store and Google Play reviews (Oviva and other brands with an app)

- **Google Play** (`gd_m6zagkt024uwvvwuyu`): app URL, plus `num_of_reviews`, `country`,
  `language`, `start_date` and `end_date`. The date range gives incremental runs, and country and
  language suit a brand like Oviva that runs in several countries. Output includes rating, text,
  date, helpful count and the app's overall rating, review count and download band.
- **Apple App Store** (`gd_m734msue16e0adkbit`): the app URL is the only input. The country is
  part of the URL (`apps.apple.com/de/app/...`), so each country store is its own URL. There is
  no date or count input, so we don't know yet how many reviews a call returns, and the first
  paid call must use one app in one country. Output includes the **developer's reply** to each
  review.

### Yahoo Finance, for listed companies

`Yahoo Finance business information` (`gd_lmrpz3vxmz972ghd7`) returns **company and market data,
not news**: price, market cap, P/E, earnings date, analyst rating and price target, sector,
headcount, key executives, quarterly financials, and revenue and earnings estimates. It takes a
quote URL, or `discover_by_keyword` with a ticker such as `MSFT`.

- Neither Brand Watcher nor the Market Monitor stores a ticker today. Wikidata has one for most
  listed companies (property P249), and Brand Watcher already checks brands against Wikidata, so
  we could take the ticker from there for free.
- The useful signals for a listed brand would be the earnings date, analyst rating changes and
  price-target changes, as alert triggers next to its news.
- For news about a listed company, the free `search_engine` and `scrape_as_markdown` tools can
  search Yahoo Finance or Reuters pages directly.

### Reuters news

The dashboard lists a "Reuters News" tool, but the live server doesn't offer it, and the scraper
catalog has no Reuters scraper under "reuters", "news" or "Reuters". Bright Data seems to have
dropped it when it replaced the per-site tools with `run_scraper`. Where it existed, it read one
Reuters article from its URL, so it was never a news search feed like NewsAPI.

For Reuters coverage we have two options:
- the free `search_engine` with `site:reuters.com <query>`, then `scrape_as_markdown` for the
  article text. This counts against the 5,000 free calls a month.
- asking Bright Data whether the Reuters dataset still exists outside MCP.

### What AI assistants say about a brand (from Bright Data's docs, 13 Oct 2026)

Bright Data's MCP server has a `geo` group with two tools, `chatgpt_ai_insights` and
`perplexity_ai_insights`. Each sends a prompt to that assistant and returns its answer. The
scraper catalog also has `Gemini Search` (`gd_mbz66arm2mf9cu856y`) and `Google AI Mode Search`
(`gd_mcswdt6z2elth3zqr2`).

For Brand Watcher, this would let a brand ask a fixed set of buyer questions ("best weight-loss
programme in Germany", "most comfortable gaming headset") every week. It could then track whether
the brand is named, where it ranks against competitors, and what the answer says about it. For the
Market Monitor, it shows which vendors the assistants recommend in a category. Neither product
measures this today. The prices of the `geo` tools are not on the dashboard, and we have not
looked at their inputs yet.

### LinkedIn people search by filter

`search_dataset` searches Bright Data's stored LinkedIn people and company records by filter,
with no scrape, and returns 10 records per call. For the Market Monitor it could count a vendor's
staff by role, such as how many sales or engineering people work there. That is a stronger growth
signal than the headcount band on a company page. The dashboard doesn't give its price, and the
stored records may be weeks or months old.

## Rough cost

Take G2 for the AI Security market's 53 vendors, at an average of 10 new reviews per vendor per
week. That comes to about 530 records, or about $1.30 a week, if there is no minimum per call.
Reviews arrive slowly, so review sources are cheap once the first full pull is done. The first
pull is the larger cost: some vendors have hundreds of reviews, so `pages` or `start_date` should
cap it.

## Suggested order

1. **G2 for the Market Monitor**, on the bugfixing AI Security market. It is the clearest gap:
   buyer reviews are the one view of a vendor we have nothing for.
2. **App Store and Google Play reviews as a Brand Watcher source** for any brand with an app,
   starting with Oviva. Asked for on 13 Oct 2026.
3. **Amazon product reviews** for consumer-product brands, set up for the headset prospect's demo.
4. **Trustpilot**, for any brand that has a Trustpilot page.
5. **YouTube by keyword** for brand mentions.

## Before any of these is built

- **Confirm whether MCP scraper calls carry a minimum charge per call.** This decides whether we
  can fetch one vendor at a time or have to batch every vendor into one call, as the LinkedIn
  datasets do now.
- **Check how `run_scraper` behaves.** It waits up to 45 seconds, then hands back a snapshot ID to
  collect later. Scheduled jobs must handle the "still running" case, as the dataset triggers do.
- **Allowlist the tool and dataset.** Each source gets its own entry naming the tool and dataset
  it may call. No agent path gets `run_scraper` (see the web access spec).

## Test call, 13 Oct 2026: Google Play, Oviva

We sent one paid call: `run_scraper` on `gd_m6zagkt024uwvvwuyu`, app `com.rementr` (Oviva),
`num_of_reviews: 5`, `country: "DE"`. Snapshot `sd_mv72982jnx6gz1cnh`.

- **It worked first time.** We got 5 records and no errors, and the call came back in about 4
  seconds with status `ready`, so this scraper does not need the "still running" path.
- **The response carries no cost figure.** Whether a minimum charge applied has to be read from
  the Bright Data dashboard's usage page for that snapshot.
- **Without `language`, the reviews came back in English** although `country` was `DE`. German
  reviews need `language: "de"`.
- **The reviews were not newest first.** Dates ran 18 Sep, 24 Aug, 22 Jul, 22 Jul, 13 Sep. So
  scheduled runs must pass `start_date` to get new reviews, not rely on `num_of_reviews`.
- **The app-level fields are useful on their own:** rating 4.41 from 30,673 reviews, and 413,668
  downloads. Taken weekly, these give a rating trend for free alongside the reviews.
- **`app_developer` is wrong.** It says "Google Commerce Ltd", so we should not store that field.
- **The `tools=` URL parameter works.** With `tools=run_scraper,...` the server offered exactly
  the four tools named.
- **`search_engine` ignored `site:`.** The query `Oviva app site:play.google.com` returned
  unrelated apps. The plain query `Oviva app Google Play` found the right page. URL-finding must
  check the domain of each result itself.
