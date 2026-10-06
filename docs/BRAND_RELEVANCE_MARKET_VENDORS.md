# Brand decisions for market vendors

Status: draft for review, 2026-10-06. Extends `docs/BRAND_RELEVANCE_SPEC.md`
(the adopted brand relevance spec) to articles that reach a vendor through a
Market Monitor rather than through a brand topic. Requested by Oliver for
panaya ("option 2"); nothing here is built yet.

## 1. Why

The brand decision (profile, exclusions, ownership, mention, judge, headline
rule) runs only on brand topics: keyword groups named "Brand Monitoring X" or
"X - Brand Watch". Panaya has no such groups. Its seven vendors are collected
through one market topic, "Market Monitoring Enterprise Test Automation", and
the Market Monitor links articles to vendors with its own name match. So on
panaya the brand flag is on but no brand decision is ever made, and every
vendor count still rests on the old substring match.

The same name match runs on every site with a Market Monitor:

| Site | Market | Name-match links, last 30 days | Vendors |
|---|---|---|---|
| bugfixing | AI in the SOC (aisocnews.com, public) and two others | 1,231 | 85 |
| sunstar | Oral Care | 327 | 6 |
| panaya | Enterprise Test Automation | 228 | 11 |
| abm | Media & Narrative Intelligence | 88 | 8 |
| oviva | Oviva | 77 | 6 |

## 2. How a vendor link is made today

Three writers put rows in `bw_article_categories` for market vendors. Only the
first is in scope.

1. **Name match** (`market_corpus.attribute_vendors`, method
   `market_name_match`). Runs inside the corpus scan (`market_corpus.scan`,
   called by `app/tasks/market_monitor.py` and the manual scan route). It
   looks for a vendor's reviewed names and products in the title and summary,
   applies the market context gate (the market qualifier or one of the
   market's phrases must appear, unless the name cannot be a dictionary word
   or the page is on the vendor's own site), then writes the vendor link, the
   `bw_market_articles` row and the entity-layer link, in that order.
2. **Vendor LinkedIn posts** (`market_collect.attribute`, method `market`).
   Attributed by the account they came from, which is exact. Owned social,
   already outside earned news. Out of scope.
3. **Owned pages** (`attribute_owned_pages`, method `owned_domain`). Pages on
   a vendor's own site. Out of scope: ownership is already exact.

Readers count links. The market overview, share of voice, vendor lists and
entitlements use `market_corpus.earned_sql` (not the vendor's LinkedIn, not
the vendor's own domain). Brand Watcher on the same site uses
`brand_coverage`. Neither reads a brand label for these links today.

## 3. What panaya's links look like under the brand rules

Measured 2026-10-06 on all 228 existing name-match links, with the brand
profile's mention detector and ownership rule and no model calls:

| Result | Links | What happens under this spec |
|---|---|---|
| Independent, vendor in the headline | 111 | judged, with the headline rule as the floor |
| Vendor's own site | 86 | not earned (readers already exclude them) |
| Independent, vendor only in the body | 11 | judged: kept only as subject or notable |
| Independent, no recognisable mention | 7 | not linked |
| Vendor not an enabled Brand Watcher brand | 12 | profile built anyway (section 5.1) |
| Automated valuation page | 1 | not linked |

The seven unrecognised mentions are all UiPath, matched through its generic
product names ("Test Suite", "Test Manager", "Test Cloud") in developer posts
about testing. The effect on panaya is therefore modest: it removes false
product matches and passing mentions, and leaves headline coverage alone.

## 4. The rule

For each (article, vendor) pair the name match finds, after the existing
context gate:

1. Resolve the vendor's brand profile by brand id (section 5.1).
2. Run the existing decision (`brand_decision.decide`) unchanged:
   exclusions, ownership, mention, reuse, judge, headline rule. Same labels,
   same policy and rubric versions, same judge route and hourly budget.
3. Write the vendor link only when the decision is **earned** (subject or
   notable, independent source). Every decision, kept or not, is stored
   (section 5.2).

What happens to each outcome:

| Decision | Vendor link | Market corpus row | Entity link |
|---|---|---|---|
| Earned | written | written | written |
| Owned | left to `attribute_owned_pages` | unchanged | unchanged |
| Fan site (`fan_content`) | not written | written | not written |
| Sector, passing, other | not written | written | not written |
| Unavailable (judge failed) | not yet; retried | written | not yet |
| Deferred (profile problem) | not written; reported | written | not written |

The market corpus row (`bw_market_articles`) is kept for every outcome,
because the article is still about the market. Only the claim "this vendor
was covered" depends on the decision. The vendor link and the entity link
are written together or not at all, so the two stores that must agree
(overview and vendor page) keep agreeing.

Deal listings count as coverage and carry `evidence.promotional`, as decided
for brand topics on 6 Oct.

Social posts that name a vendor (Bluesky, Reddit and other discussion
sources) keep today's rule in this version. The brand spec keeps social out
of news classification, and the market treats discussion as its own channel.

## 5. Design

### 5.1 Profiles

`brand_profile.load_rows` loads enabled brands. A market vendor may be a
`bw_brands` row that Brand Watcher has switched off (panaya: ACCELQ,
Applitools, Avo Automation, Leapwork). The market path builds the profile
from the vendor's row by id whether or not it is enabled, because the market
tracks it. Duplicate or missing profiles defer, as on brand topics.

Generic product names need context. UiPath's "Test Suite", "Test Manager" and
"Test Cloud" become `ambiguous_aliases` with `mention_context` ["UiPath"] in
panaya's profile file. The same review applies to every market before its
flag goes on (section 7).

### 5.2 Storage

A new table, by Alembic migration:

`brand_article_decisions` (article_uri, brand_id, market_id, brand_relation,
source_relation, outcome, judge_version, decision_evidence JSONB,
last_failure JSONB, decided_at), unique on (article_uri, brand_id).

Brand-topic decisions stay in `keyword_article_matches`, which is scoped per
keyword group. A market group covers many vendors, so one match row cannot
hold one label per vendor. A separate table keyed by article and vendor is
the smallest correct store.

Reuse looks in both stores. A brand-topic decision and a market decision for
the same article, vendor and inputs (same reuse key) share one judgment, so
sites that have both (sunstar, oviva) never judge a pair twice.

### 5.3 Readers

No reader query changes. Readers count links, and only earned decisions write
links. Two additions:

- `brand_coverage.coverage_split` also reads `brand_article_decisions`, so the
  Brand Watcher coverage panel shows market vendors' buckets instead of
  "decided before labels".
- The market report's change panels ("Who moved", previous-period table,
  earned delta) already wait for `collection_started`. They will also wait
  for the market's decision start date (section 6), so a fall in counts
  caused by the stricter rule is never reported as a fall in coverage.

### 5.4 Failures and retries

A failed judgment stores outcome `unavailable` and writes no link. The retry
(`brand_retry`, via the enrichment sweep or the cron) also selects market
decisions that are unavailable, under the same attempt cap. It re-decides the
pair directly and writes the link if earned; the ingest pipeline is not
involved, because the article is already stored and enriched.

### 5.5 Switch

A new per-site flag, `MARKET_VENDOR_DECISIONS`, default off. Off means the
name match behaves exactly as today. It is separate from
`BRAND_RELATION_DECISIONS` because it changes Market Monitor numbers,
including the public aisocnews.com site.

On switch-on, the market's `config.vendor_decisions_since` is set to the
switch-on time. It is the date section 5.3's change panels wait for.

## 6. Existing links

Existing links are not rescored or removed. A script,
`scripts/market_vendor_decisions_audit.py`, makes the decision for existing
links in dry-run mode and reports, per vendor, how many it would keep, drop
or leave unavailable, with samples. Removing or relabelling old links is a
separate decision for Oliver, made from that report.

## 7. Rollout

1. Build in canonical behind the flag, with tests (section 8).
2. Panaya: profile review (UiPath's generic product names), migration,
   audit report, flag on, inspect the next scan.
3. Every other market only on Oliver's say-so, each after its own profile
   review and audit report. Bugfixing's AI in the SOC market feeds the public
   aisocnews.com site and its paid dataset, so it is decided separately and
   last.

## 8. Tests

- The rule table in section 4: one test per outcome, checking the vendor link,
  the market corpus row and the entity link together.
- Flag off: the name match writes exactly what it writes today (same rows,
  same methods), on a captured panaya sample.
- Disabled vendors get a profile; missing or duplicate profiles defer.
- UiPath's generic product names need "UiPath" nearby (the seven captured
  developer posts are not linked; a captured UiPath "Test Suite" press story
  is).
- Reuse across stores: a pair decided on a brand topic is not judged again by
  the market scan, and the reverse.
- Retry: an unavailable market decision is retried, counted against the cap,
  and writes its link when the retry is earned.
- `coverage_split` merges both stores and counts an article once per vendor.
- Change panels wait for `vendor_decisions_since`.
- Database tests run in a throwaway schema, as the existing brand store tests do.

## 9. Cost

One judge call per independent body or headline mention not already decided:
on panaya about 122 for the existing backlog if the audit runs live, then a
few a day (its busiest day this month had 29 name-match links). On bugfixing's SOC market at most
about 40 a day (1,231 links in 30 days, before owned pages are set aside). Same model and hourly budget as brand topics (`HYBRID_RELEVANCE_LLM_MODEL`,
600 calls an hour).

## 10. Decisions for Oliver

1. **Sector and passing mentions of a vendor stay unlinked.** The article
   stays in the market corpus, but the vendor is not credited. This lowers
   vendor mention counts on roundup-heavy markets. Recommended: yes,
   consistent with brand topics.
2. **Existing links stay as they are** until the audit report is read.
   Recommended: yes.
3. **Panaya only for now.** Recommended: yes; aisocnews last and separately.
