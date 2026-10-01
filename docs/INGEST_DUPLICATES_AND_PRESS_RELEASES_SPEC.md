# Spec: duplicate articles and press releases at ingest

Status: built on bugfixing, 1 October 2026 (see "As built" at the end)
Sites: bugfixing, then wiley and wileytest (monolith copy rule)

## Summary

Topic feeds show the same story several times and treat paid press releases as news. Both have
the same cause. The only check at insert is an exact URL match, and the only filter that keeps an
article out of the feeds is the topic relevance score. A copy of a story at a slightly different
URL counts as new. A press release about the topic scores as relevant, because it is about the
topic.

The fix labels both at insert time and leaves every row in place:

1. **Same article at a different URL** (tracking parameters): this is the same row, so we don't
   insert it again.
2. **Same story on another outlet** (syndication, wire copies, a second slug): we insert it and
   mark it as a copy of the first one we saw. Feeds show the first copy and can say "also in N
   outlets".
3. **Press releases**: we tag the source type at insert, using the wire list that reports
   already use. Each topic decides whether its feed shows them.

## What went wrong on 1 October

These came from the "European Battery Industry" topic built for the PowerCo call. Each one got
into the feed:

| What the feed showed | Why it got through |
|---|---|
| Seeking Alpha's €3.22B story twice, one URL with `?feed_item_type=news` | Exact URL match only. `feed_item_type` is not on any tracking-parameter list. |
| ara.cat's Gotion story twice, two slugs with the same article ID `_1_5863460` | Different URL. The titles differ by two words. |
| Asia Times story repeated on menafn.com | Different domain. The titles are identical apart from case. |
| GlobeNewswire and openPR market-report releases | They scored 0.4 and 0.5 on topic relevance, and the floor is 0.4. Nothing checks what kind of source it is. |

## How big the problem is

These counts cover articles that passed the AI analysis step and the relevance floor in the last 30 days.
"Same title" means identical after lowercasing and stripping punctuation, within one topic.

| Site | Readable articles | Same title repeated | Same URL apart from query string | From a press-release wire |
|---|---|---|---|---|
| bugfixing | 6,202 | 442 (7%) | 2 | 84 (1.4%) |
| wileytest | 18,517 | 2,112 (11%) | 57 | 1,249 (6.7%) |

On wileytest the most repeated titles are AP wire stories, with one carried by 29 outlets. The
"same title" figure includes those, so it gives the order of magnitude rather than an exact count.
The near-match rule below catches more than exact titles, so the real figure is higher.

## What already exists and should be reused

- **`app/services/daily_briefing_ranking.py`**
  - `normalize_uri()` strips the scheme, `www.`, tracking parameters, the fragment and the
    trailing slash.
  - `normalize_title()` and `title_similarity()` compare titles. The similarity measures how much
    of the shorter title the longer one contains, and the briefing composer treats 0.85 or more as
    the same story.
  - Tested on the 1 October pairs: ara.cat scores 1.0, Asia Times/menafn scores 1.0 (and the
    normalised titles are equal), and Seeking Alpha scores 1.0. Two different VW–Gotion stories
    ("Volkswagen Taps Gotion…" against "Volkswagen Is Going Big On Cheaper LFP…") score 0.43,
    which is correctly below the bar.
- **`app/services/report_corpus.py`**: `is_wire_host()` and the `_DEFAULT_WIRE_SOURCES` list
  (prnewswire, businesswire, globenewswire, openpr, prtimes, presseportal, menafn and others,
  overridable with `REPORT_WIRE_BLOCKLIST`). Reports, market post review and entity coverage
  already use it. It correctly flags globenewswire, openpr and menafn, and correctly passes
  asiatimes.
- **`app/services/article_visibility.py`** is the one rule for whether an article row is
  readable. The facade readers and both pgvector searches use it, so a change there reaches
  Auspex, the MCP tools and the feeds at once.

Two gaps in the existing helpers:

- `normalize_uri()` keeps `feed_item_type` and `cid`. Zacks uses `?cid=`. Both need adding to
  `_TRACKING_PARAMS`.
- The helpers live in briefing and report modules. Ingest should not import from those, so we
  move the helpers into a shared module and leave the old names importing from it.

## Design

### 1. Shared module

Create `app/services/story_identity.py`:

- `story_url_key(uri)`, which wraps `normalize_uri()` with the extended tracking list
- `title_similarity()` and `normalize_title()`, moved from `daily_briefing_ranking.py`, which
  keeps importing them
- `source_type(uri, news_source)`, which returns `"press_release"` when `is_wire_host()` matches
  the URL host or the source name, and `"news"` otherwise. `is_wire_host` and the wire list move
  here too, and `report_corpus.py` keeps its public names by importing them.

### 2. New columns on `articles` (Alembic migration)

| Column | Type | Meaning |
|---|---|---|
| `url_key` | text, indexed | `story_url_key(uri)` |
| `duplicate_of` | text, nullable, indexed | URI of the first copy we saw of the same story in the same topic |
| `source_type` | text, nullable | `news` or `press_release`. NULL means not yet classified. |

We store `duplicate_of` rather than deleting the copy, because the number of outlets carrying a
story is information in its own right (AP stories, consensus counts). The ingest step already keeps
relevance rejects for the same reason.

The migration is plain DDL. The sites' Alembic histories have diverged, so we check each site's
Alembic head before applying it, and we give it an explicit revision ID.

### 3. Insert path

Both insert paths in `app/database_query_facade.py` get the same three checks:
`create_article` (line ~441, used by the keyword monitor) and `upsert_article` (line ~5107).

1. **URL key.** Before inserting, look up `url_key` within the same topic. If it matches, treat
   the article as existing, exactly as an exact URI match is treated today. No new row.
2. **Same story.** Look for an earlier row in the same topic, published within 3 days either side,
   where `normalize_title` is equal or `title_similarity` is 0.85 or more. If one is found, insert
   the new row with `duplicate_of` set to the earliest such row's URI. The earliest row stays the
   original. Only originals are candidates, which keeps chains one level deep.
3. **Source type.** Set `source_type` from `source_type(uri, news_source)`.

Step 2 runs at insert, before the AI analysis step. That means a copy can also skip analysis: it
copies the original's analysis fields instead of paying for another model call. This is optional
and goes behind a flag (`DUPLICATE_SKIP_ANALYSIS`), because a syndicated copy sometimes carries
extra paragraphs.

The title lookup must be cheap. It only searches the same topic over a 6-day window, using an
index on `(topic, publication_date)`. It needs measuring on wileytest, the largest site.

### 4. Who sees what

- **`readable_clause()`** adds `duplicate_of IS NULL`. That one change takes copies out of feeds,
  search, Auspex and MCP.
- **Feeds** show an "also in N outlets" count on the original, from
  `count(*) WHERE duplicate_of = uri`.
- **Press releases** are controlled per topic by a new topic setting, `include_press_releases`
  (default below). When it is off, readers add `source_type IS DISTINCT FROM 'press_release'`.
  When it is on, the feed shows a "Press release" label on the card.
- **Analytics and training** (`get_vectors_by_metadata`, retraining, propagation counts) keep
  reading everything, as they already do via `readable_only=False`.

### 5. Backfill

Write `scripts/backfill_story_identity.py` with `--dry-run`, `--site-days N` and `--topic`. It
fills `url_key` and `source_type` for every row, then walks each topic in publication order to set
`duplicate_of`. A dry run prints the pairs it would link, with a sample of 50 for checking by eye.

## Rollout

1. Build on bugfixing: shared module, migration, insert path, readers, backfill script, tests.
2. Dry-run the backfill on bugfixing and wileytest. Check 50 linked pairs on each by eye. Proceed
   only if fewer than 1 in 50 are different stories. Per the propagation lesson, we judge by the
   precision of the linking, not by how many rows it hides.
3. Run the backfill on bugfixing. Check the European Battery Industry feed against the four cases
   in the table above.
4. Copy to wiley and wileytest: migration first, then code, then restart when quiet, then the
   backfill. wileytest is the paying customer, so it goes last and gets its own sample check.

Estimated build time for an AI agent: about 2 hours for steps 1–3, plus about 1 hour per extra
site, most of it waiting for quiet restart windows and the sample checks.

## Tests

- **Unit tests** for `story_url_key`, covering the Seeking Alpha and Zacks query strings, and for
  `source_type`, covering globenewswire, openpr and menafn as press releases, asiatimes as news,
  and "PR Newswire" as a bare source name.
- **Linking tests** using the four 1 October pairs as fixtures. Three must link. The two different
  VW–Gotion stories (similarity 0.43) must not link.
- **Insert test**: inserting the `?feed_item_type=news` URL after the clean one creates no row.
- **Reader test**: a copy and a press release in a topic with `include_press_releases` off are
  both absent from `get_articles_by_topic`, and both are present with `readable_only=False`.

## Decisions for Oliver

1. **Press-release default.** Should the topic feed show press releases by default? My
   recommendation is off for ordinary topics and on for Market Monitoring topics, where vendor
   releases are the point.
2. **Skipping analysis for copies.** Should copies reuse the original's analysis instead of paying
   for a model call each? It saves cost on AP-heavy topics. The risk is a copy that adds material.
3. **Which copy is the original.** Should the original be the first copy we saw, or the outlet we
   rank higher? First-seen is simpler. Ranking needs a source-credibility list, and 18 of 24 rows
   in the PowerCo topic had no credibility rating.

## As built on bugfixing (1 October 2026)

Decisions taken: press releases are hidden by default and shown in Market Monitoring topics. The
first copy we saw is the original. Copies still get their own AI analysis: the
`DUPLICATE_SKIP_ANALYSIS` option was not built.

Where the build differs from the design above:

- **The helpers were not moved.** `app/services/story_identity.py` imports `normalize_uri`,
  `normalize_title`, `title_similarity` and `is_wire_host` from their current modules. Both of
  those modules are plain Python with no heavy imports, so ingest can use them as they are, and
  the briefing code is untouched.
- **The feeds needed their own filter.** The news feed, Explore and the category lists never used
  the readable rule. Applying it there would also have added the 0.4 relevance floor to those
  views, which is a separate change. They now apply `story_clause()` / `story_sql()` from
  `article_visibility.py`, which only hides copies and press releases:
  - `get_news_feed_articles_for_date_range` and its count, and `get_news_feed_articles_chronological`
    and its count (the news feed, dashboard, ticker and six-articles view)
  - `get_articles_with_dynamic_limit` (the article sample Explore's analysis is built from)
  - the three category queries in `app/routes/news_feed_routes.py`
- **The readable rule** (`readable_clause` / `readable_sql`) gained both checks, which covers the
  facade readers, search, Auspex and the MCP tools.
- **A copy is hidden only when its original is readable.** If the original was rejected by the
  relevance check, or is a press release this topic hides, the copy stays visible. This means we
  never lose a story because the wrong copy came first. Example: the Seeking Alpha "sells 5.3%
  stake" piece links to an investing.com copy that scored 0, so Seeking Alpha stays visible.
- **Gather is not filtered.** It is the view for checking everything that was collected, rejects
  included.
- **Fourteen code paths insert articles.** The two main facade paths (`create_article`,
  `upsert_article`) label at insert. The keyword monitor then runs `label_unlabelled()` after
  every group check, which labels rows from any other insert path, oldest first.
- **A row only links to an earlier, already-labelled original**, so chains cannot form.
- **The topic setting** is `"include_press_releases": true|false` on a topic in `config.json`.
  When the key is missing, Market Monitoring topics default to true and every other topic to false.
- **Not built:** the "also in N outlets" count on feed cards (it needs a UI change), the
  `DUPLICATE_SKIP_ANALYSIS` option, and the Auspex brand fallback and MCP social query (rows 15
  and 19 of the reader survey).

### Matching limits found by checking samples by eye

The briefing composer's title rule was not strict enough on its own. The first 50-link sample on
bugfixing had 3 wrong links (6%), and the second had 3 more of a different kind. Each wrong link
led to a rule:

| Wrong link | Rule added |
|---|---|
| "Editorial" and "Editorial", two different papers | Equal titles need at least 3 significant words. |
| "AP Technology SummaryBrief at 6:33 p.m." and "at 6:07 p.m." | When titles differ, the numbers in them must be the same. |
| "Radware Reports Second Quarter 2026 Financial Results" and PTC Therapeutics' release with the same wording (86% contained) | Press releases only link when the titles are equal. |
| "Israel strikes Hezbollah targets in Lebanon" and a different strike story | A near match needs at least 6 significant words, not 5. |
| Two Bluesky accounts posting the same Swiss news | Social posts link on URL only, never on title. Two accounts are two voices. |

The third sample of 50 (seed 23) had no wrong links. Result on bugfixing: of 237,632 rows,
14,799 are copies (6%) and 8,392 are press releases. A full relabel takes about 22 minutes.

Run `SAMPLE_SEED=<n> scripts/backfill_story_identity.py --sample 50` with a new seed on each site
before switching it on.

Migration `si_001` (down revision `mm_032` on bugfixing). Backfill:
`scripts/backfill_story_identity.py`, with `--sample N` to print links for checking by eye.
Tests: `tests/test_story_identity.py`.

## wiley and wileytest (1 October 2026)

- **Press releases stay visible there for now.** Both sites set `STORY_PR_DEFAULT=show`, so every
  topic without its own `include_press_releases` key keeps showing press releases. On wileytest,
  wire releases are 11% of readable M&A Updates articles over 90 days and 19% of Patent Cliffs,
  and for a deal or a filing the release is often the primary source. Copies are hidden there as
  on bugfixing. Which topics should hide press releases is the customer's call.
- **`is_wire_host` is missing there.** Their `report_corpus.py` predates it, so
  `story_identity.py` falls back to the same check over their wire list plus menafn.
- **Migration `si_001` revises `vp_001`** on both sites, which are behind bugfixing's `mm_032`.
- **`.env` is rebuilt at every start** from `.env.encrypted` by `env_encryption.py decrypt`. A
  setting added to `.env` must be re-encrypted (`env_encryption.py encrypt <site>`, which deletes
  the plain file) before the restart, or the restart wipes it.
