# Data quality review: Panaya, Sunstar, Oviva

_5 October 2026. Window: the last 14 days of collection on each site. Every number below was read from the site's database or its service log today; where the cause needed it, we fetched the source pages or queried the provider directly._

## The short version

The three sites collect far more than they keep, and most of what they reject is noise the collectors should never have fetched. The relevance gate is doing its job; the waste and the risk sit upstream, in how keywords reach the providers, and downstream, in a few rows that never get the metadata the product needs.

| Site | News rows in 14 days | Approved | Social rows | On-brand social | Observer pool, last 3 days (news / social) |
|---|---|---|---|---|---|
| Panaya | 2,207 | 193 (9%) | 1,586 | 1,179 | 23 / 219 |
| Sunstar | 2,321 | 130 (6%) | 6,906 | 2,396 | 32 / 811 |
| Oviva | 408 | 49 (12%) | 729 | 254 | 10 / 89 |

Ranked by how much each hurts the customer-facing output:

1. **Multi-word keywords reach TheNewsAPI unquoted**, so the provider matches the words anywhere in the article body, not the phrase. This is the largest noise source on all three sites. (Fix: data, small.)
2. **Panaya's and Oviva's social observer pools are mostly LinkedIn company posts** carrying a hard-coded relevance of 1.0, no sentiment and no author role. (Fix: code, medium.)
3. **Sunstar's native reddit posts have no social metadata**, so 371 posts in 14 days are invisible to the Social tab, the observers and the briefing. (Fix: copy one file, small.)
4. **Bare or borrowed keywords** pull car auctions, recipes, a networking vendor and a subreddit name into the news pool. (Fix: data, small.)
5. **Duplicates and press releases are not labelled** on these sites; the 1 October build exists only on bugfixing, wiley and wileytest. (Fix: deploy, medium.)
6. **Japanese body-text phantoms** from TheNewsAPI. Guard deployed today; listed for completeness.
7. **Collector health**: a shared NewsData key that runs out of credits mid-day, two dead Noom feeds retried every few minutes, arXiv and Semantic Scholar refusals, and a quality score that is a constant placeholder.

Nothing here changes what a customer has already received. The briefings and observer reports are built from the approved pool, and that pool is clean. What the findings change is how much of the real signal reaches that pool, how much quota we burn to get there, and what the counts on the dashboards mean.

## 1. Unquoted phrases: the provider matches words, not phrases

**What we saw.** Of Panaya's 1,990 market-topic news rows, only 4% contain the keyword that matched them in the title or summary; 62 were approved. The keywords with the most rows all reject at 98% or more: "continuous testing" 174 rows, "autonomous testing" 171, "business process testing" 165, "agentic testing" 137, "test automation funding" 125. Sunstar's "oral care market" produced 384 rows and 16 approvals; Oviva's "Second Nature" 162 rows and none.

**Why.** TheNewsAPI treats a space as AND and, since 31 August, searches article bodies. "continuous testing" therefore returns any page with "continuous" and "testing" anywhere in it. We fetched a sample of rejected pages: in most, the two words appear far apart, and in about a third neither the phrase nor the words appear at all. Querying the provider directly over seven days:

| Keyword | Unquoted, body search | Quoted, body search |
|---|---|---|
| continuous testing | 281 | 6 |
| business process testing | 295 | 0 |
| agentic testing | 175 | 2 |
| oral care market | 42 | 2 |
| oral health heart health | 23 | 0 |

**Fix: none. Measured and rejected the same afternoon.** Quoting looked like the obvious fix, so before changing a keyword we fetched the pages of every article approved in the last 30 days and checked whether the keyword phrase is on the page at all. It is not, for most of them. On Panaya, of 39 approved pages that could be read, 18 carry the phrase and 21 match only on separate words; the 21 include real finds such as "Synthesized Launches UiPath Integration to Automate Test Data Provisioning" and "TestMu AI Launches Test Deduplication Agent". On Sunstar's US group, 4 of 21 carry the phrase; the 17 that would be lost include "Can Gum Disease Increase Alzheimer's Risk? Study Finds Bacteria in Brain", which is the topic. The loose matching is what delivers the recall. Its price is about 95% noise per keyword, which the relevance gate rejects on nova-lite at a fraction of a cent per article, plus provider quota. Quoting would cut the noise and more than half of the yield with it. Leave the keywords as they are; treat the collected-versus-approved ratio on these groups as the normal shape of body search, not as a fault. The one exception is a brand name made of common words ("Weight Watchers"), where 82% of approved articles carry the exact phrase and the separate words pull car auctions; that one is quoted now on Oviva.

## 2. LinkedIn posts: in every pool, judged by nobody

**What we saw.** The Market Monitor's LinkedIn collection stores company-page posts with topic "<Brand> - Brand Watch", relevance 1.0, no ingest status, no sentiment and no author role: 358 on Panaya, 45 on Sunstar, 37 on Oviva in 14 days. Because the observers admit any social post at relevance 0.4 or above, every LinkedIn post enters every observer's pool. On Panaya, LinkedIn is most of the 219 on-brand social posts the observers saw in the last three days.

Side findings: Panaya's five dropped peer vendors (Leapwork, Opkey, ACCELQ, Avo, Applitools) still show 105 LinkedIn posts, all from 21 and 22 September, the days before they were dropped; nothing newer, so collection did stop. Each brand ends up with two topic names, "Brand Monitoring X" for everything else and "X - Brand Watch" for LinkedIn, which splits the brand's material across views.

**Fix.** Either run LinkedIn posts through the social evaluation (sentiment, author role, relevance against the brand like every other platform), or mark them as owned so the observers and the Voices panel can treat them as the brand's own voice. Unify the topic name. Medium: a day of agent work, because the observer queries, the Social tab and the Voices classifier all read these fields.

## 3. Sunstar's reddit posts carry no social metadata

**What we saw.** Sunstar's consumer-voice group collects reddit two ways. Posts that arrive through Xpoz (852 in 14 days) carry social metadata. Posts from the native reddit collector (371) do not: they are stored as news, get status "social_evaluated" and relevance about 0.3, and then match nothing. The Social tab keys on social metadata, the observers' social branch requires it, and the news branch requires a category. Those 371 posts are invisible everywhere.

**Why.** The reddit collector on Sunstar is an older copy. The canonical one attaches platform, external id and author on every post; Sunstar's does not.

**Fix.** Copy `app/collectors/reddit_collector.py` from canonical, restart, and backfill the metadata on the stored rows from their URLs (subreddit and post id are in the path). An hour of agent work including the backfill.

## 4. Bare and borrowed keywords

**What we saw**, rows and approvals in 14 days:

| Site | Keyword | Rows | Approved | What it pulls |
|---|---|---|---|---|
| Oviva | Juniper | 117 | 0 | Juniper Networks, TechRepublic |
| Oviva | "Second Nature" | 162 | 0 | a phrase used everywhere |
| Oviva | Weight Watchers | 97 | 11 | car auctions (bringatrailer.com, 55 rows), recipe blogs |
| Sunstar | askdentists | 214 | 0 | a subreddit name sent to the news providers |
| Sunstar | Dentistry | 155 | 0 | a bare word |
| Sunstar | Lion Corporation (English group) | 90 | 0 | "lion" matches anything |
| Sunstar | 口腔 全身疾患 | 133 | 0 | see section 6 |

**Fix.** Apply the 30 September prune rule (drop a keyword when under 10% of its rows pass and fewer than 100 pass), with two refinements. A competitor's name is never dropped, it is qualified: "Juniper weight loss", "Second Nature" plus a programme word. A subreddit name belongs to the reddit collector only; the group's other providers should not search for it. Half an hour per site.

## 5. Duplicates and press releases are unlabelled here

**What we saw.** Same-title copies on different URLs: Sunstar 198 extra rows (8.5% of news), Panaya 81 (3.7%), Oviva 26 (6%). The copies are wire syndication across local papers. Press-release wires are about a tenth of news volume and almost never approved: globenewswire 160 rows and 6 approvals on Panaya, 133 and 0 on Sunstar; openpr 91 and 3, 83 and 0.

**Why.** The ingest build that labels copies and press releases at insert (`docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md`, built 1 October) is on bugfixing, wiley and wileytest only. These three sites lack the `duplicate_of` and `source_type` columns and the insert-time labelling.

**Fix.** Deploy that build to the three sites: the migration, the facade insert paths, `article_visibility.py`, the monitor's labelling pass, and a backfill. Half a day of agent work with verification. A cheaper interim step is to exclude openpr and globenewswire from the non-market topics on Sunstar and Oviva; Panaya's market topic should keep wires, because vendor announcements arrive that way.

## 6. Japanese phantoms (guard live since today)

Of 181 Japanese rows in one week, 111 pages did not contain the search term anywhere; TheNewsAPI's Japanese body index matches loosely. A guard now fetches the page once for new results in Japanese, Chinese or Korean groups when the term is missing from title and summary, and drops the article if it is not on the page. It keeps every genuine match and drops about two thirds of the phantoms; the rest fail to fetch and are kept for the gate. Germany, Italy and Spain have no phantom problem.

## 7. Collector health

- **NewsData** is one shared key across sunstar, oviva, wileytest and wbm, and it exhausts its daily credits partway through each day: 181 refusals on Sunstar and 28 on Oviva in the last seven days. Groups that run late in the day get nothing from it. Fix: a key per site, or stagger the groups, or drop NewsData where TheNewsAPI covers the language.
- **Noom's two RSS feeds** return 403 on every fetch, 92 errors a week on Oviva. Disable them or find the working feed URL.
- **SmartBear's blog feed** on Panaya fails intermittently; the site's own blog is also the biggest source of approved Panaya articles (39 of 193), with UiPath's blog next (28). A third of Panaya's approved news is vendor-owned content.
- **arXiv** returned 429 and 503 on Sunstar; **Semantic Scholar** still has no API key (the 31 August form needs a browser).
- **TheNewsAPI** request volume on Sunstar is about 173 calls a day against the 100-a-day cap the collector is documented to enforce. Check the plan's real limit before it bites.
- **Quality control is a placeholder.** Every row has quality score 0.8 and no issues; the code says "Placeholder score". Any dashboard that shows it is showing a constant.
- **Enrichment failures** are small: 11 rows on Sunstar, 11 on Oviva, 1 on Panaya. Translation covers every Japanese, German, French, Italian, Spanish and Portuguese press row.
- **Sunstar's UK press group is inactive and still receives rows** (270 in 14 days, 34 approved, the best-yielding press group). The rows come through the topic's RSS feeds. Either reactivate the group so its state is honest, or note that RSS keeps it alive.

## What was done (5 October, afternoon)

- **Section 1, phrase keywords:** measured and closed without a change, as described above.
- **Section 2, LinkedIn posts and vendor blogs:** on Panaya these are deliberate, they are the competitor feed (Oliver, 5 October). Left as they are on all three sites.
- **Section 3, Sunstar reddit:** the reddit collector on Sunstar now attaches social metadata (a surgical patch; canonical's full collector needs the collector-data-quality modules the site does not have). Service restarted 17:15. The 1,065 stored native reddit posts were backfilled with platform, post id and subreddit from their URLs; 167 of them clear the 0.4 on-brand line and now show in the Social tab and the observer pools.
- **Section 4, keywords on Oviva:** bare "Juniper" and bare "Second Nature" removed from the market-watch group (163 rows, 0 approvals in 14 days); the Second Nature brand group now searches "Second Nature" weight and "Second Nature" NHS; "Weight Watchers" and "WW International" are quoted. Sunstar's "askdentists" and "Dentistry" turned out to be the reddit rows from section 3, not keyword noise; nothing to prune there.
- **Section 6, Japanese phantoms:** guard live since 16:05.
- **Section 7, feeds:** Noom's two dead feeds are disabled on Oviva. NewsData keys and the Semantic Scholar key are purchases or forms, not code.
- **Section 5, duplicates and press releases:** not deployed. The migration step was refused by the permission classifier as a production deploy, and the port needs surgical patches to three facades that have drifted from canonical (164 to 230 lines each), plus the monitor's labelling pass, the visibility helper and three route queries. It should be its own session with a test pass on one site first. The migration is additive (three nullable columns and three indexes, revision `si_001` on top of `mm_032`), so it can go first whenever that session runs.

- **Retail deal listings (found by the check, fixed the same evening):** Sunstar's brand topics had been approving price listings from deal aggregators as press, 35 rows in 90 days ("Best Deal: 4-Pack 3.8-Oz Colgate Optic White", "[Prime] Oral-B iO heads 4-Pack $19.95"), about two thirds of the Colgate topic's approvals. The relevance step now rejects a row before any model call when the host is a deal aggregator (29 hosts) or the title has a deal form: "Best Deal", "promo code", "coupon", "N% off", a price with cents that is not a headline figure, "N-pack ... toothpaste", Prime Day, Black Friday. The rule was tested on 90 days of rows on all three sites: every match was a deal page, and headline figures such as "$2.04 Billion" and "$2.73m in shares" do not match. Live on canonical, Sunstar, Oviva and Panaya (`app/services/deal_listing.py`, called at the top of `score_article_relevance`). The 35 Sunstar rows and 2 Oviva rows already approved were flipped to rejected with the explanation "Retail deal listing: not news (backfill 2026-10-05)".

One side effect to know: measuring the provider directly consumed part of TheNewsAPI's daily quota for the shared account on 5 October; the scheduled runs late that day got fewer results than usual.
