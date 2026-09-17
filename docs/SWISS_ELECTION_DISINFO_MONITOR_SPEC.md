# Swiss Election Disinformation Monitor: design spec

_Status: DRAFT for review, 2026-09-15. Net-new analysis module. Nothing built yet._

## 1. What it is for

A dashboard that answers, for the run-up to the Swiss Federal Elections of October 2027 and
the federal votes before them, five questions an analyst at a federal body, a party, a
platform or an NGO asks every morning:

1. Which false or manipulative narratives about Swiss politics are circulating right now,
   and are they growing?
2. Who is pushing them: which outlets, which state actors, which domestic amplifiers?
3. What are they aimed at: which vote, which party, which person?
4. How are they being pushed: deepfakes, bot amplification, forged documents, hijacked
   accounts, decontextualised video?
5. What has been done about it: fact-checks, platform action, statements by federal bodies?

The reference case today is the neutrality initiative vote of 27 September 2026, where
Russian state media and Swiss alternative outlets are promoting the initiative and Swiss
media are reporting on that promotion. The monitor has to work on that now, with a corpus
of a few approved articles a day, and scale to campaign volume in 2027.

## 2. What it is not

- Not a general Swiss politics dashboard. Ordinary reporting and opinion on the merits of a
  vote stay out; the topic description already says so and the relevance gate enforces it.
- Not a fact-checking tool. It records fact-checks others publish; it does not judge claims.
- Not a geographic product. Disinformation does not sit on a canton map. The one spatial
  dimension that matters in Switzerland is language region, and that gets its own panel.

## 3. Data already flowing

The module reads what the topic "Swiss Federal Elections 2027 Disinfo Monitoring" already
collects on bugfixing. It adds no new collectors.

| Source | What it carries | Set up |
|---|---|---|
| Keyword group 21 (English, firehose) | international and Swiss English coverage | 14 anchored terms |
| Keyword group 22 (German, TheNewsAPI + firehose) | the productive group, 6 approvals last week | 11 terms |
| Keyword group 23 (French, TheNewsAPI + firehose) | Romandie coverage | 8 terms |
| 20 topic-tied RSS feeds | Swiss vector outlets (Uncut-News, Les Observateurs, Arrêt sur Info), Swiss quality and alternative press (Republik, Infosperber, Journal21, Inside Paradeplatz, Schweizerzeit), five party press feeds, RSF Switzerland, and international trackers (EUvsDisinfo, EU DisinfoLab, DFRLab, Alliance4Europe, Bellingcat, Mimikama) | added 2026-09-15 |

Every article that passes the gate has `topic_alignment_score`, `category` from the topic's
14 categories, `sentiment`, `tags`, `news_source`, `language` and `submission_date`. That is
the raw material. The module adds one structured extraction per approved article (section 5).

Volume today: 1 to 3 approvals a day, 80 to 170 rejections. The design must make a quiet
week legible rather than look broken. See the Coverage panel in section 6.

## 4. What it borrows

The three existing modules share one skeleton: routes file, service class, per-article
LLM extraction, a saved narrative, a monitor task with a schedules table, and a tab of
sub-tabs in the Explore page. The monitor uses the same skeleton, registered in
`app/core/modules.py` like the others, gated by `module_config`.

| Borrowed from | What | Why |
|---|---|---|
| GeoHotspots | stat tiles + category distribution on the Overview; `extract_*_with_llm` per unprocessed article; `generate_narrative_with_llm`; DB-driven schedule table | proven shape, least new code |
| US Crisis Tracker | `/themes`, `/themes/evolution`, `/entities`, `/escalation-markers`, `/daily-intensity`, `/cooccurrence-matrix`, `/related/{uri}` | these are exactly the narrative-over-time and who-with-whom views a disinfo monitor needs |
| Threat Intel | actors table with per-actor summary; campaigns grouping several items under one operation | a vector outlet is an actor; a coordinated push is a campaign |
| Brand Watcher Voices | `audience_voices.py` role resolution over `author_role` | "who is amplifying on social" once social collection is switched back on for the topic |
| Timeline tab | `timeline_events` with `scope_type='topic'` | the election calendar and first-seen markers |

## 5. What it adds: the extraction

One LLM call per newly approved article, returning JSON. This is the whole intelligence
layer; every panel is a query over its output.

```
narratives:   [{statement, stance}]      canonical one-sentence claim the article carries or
                                         reports; stance = promotes | reports | debunks
targets:      [{type, name}]             vote | party | person | institution | policy
attribution:  {actor, confidence}        russia | china | other_state | domestic | unattributed
techniques:   [..]                       DISARM-style: deepfake, synthetic_text, bot_amplification,
                                         fake_account, forged_document, doctored_quote,
                                         decontextualised_media, astroturfing, state_media_placement,
                                         none_reported
language:     de | fr | it | en
source_tier:  state_media | alt_media | mainstream | party | fact_checker | institution | research
fact_check:   {claim, verdict, checker}  only when the article is itself a fact-check
response:     {actor, action}            only when a federal body, platform or party acted
```

Narrative matching: embed the statement, nearest-neighbour against existing
`sd_narratives` in pgvector, attach if cosine ≥ 0.85, else create a new narrative and let
the model name it. This keeps "neutrality = peace" as one narrative across German, French
and English phrasing, which is the point of the language panel.

Model: the extraction is structured JSON over a knowledge-dependent text, which the July
audit found Nova Lite hallucinates on. Use the `gpt-5.4-mini` alias (Kimi on Bedrock),
the same tier the wizard and the other modules use. At a few articles a day the cost is
negligible; at campaign volume of 50 a day it is still under a dollar a day. The weekly
brief in section 6 is prose synthesis and goes to the `gpt-5.4` alias (Sonnet-class),
once a week.

Source tier is not asked of the model for known outlets. A small table `sd_sources` maps
domain to tier and language and is seeded from the RSS feed list and the collector hits
seen so far (RT DE and uncut-news are state and alt media, Republik and NZZ mainstream,
Mimikama a fact-checker). The model only tiers domains the table does not know.

## 6. Panels

Tab id `swiss_disinfo`, label "Swiss Election Watch", icon `Vote`. Sub-tabs in this order.

**Overview.** Four stat tiles: narratives active this week, articles approved this week,
vector-outlet share of them, days to the next federal vote. Below: narrative volume by
day as stacked area by stance (promotes / reports / debunks), and the category
distribution from the topic's 14 categories. A "quiet week" state that says how many
sources were scanned and how many articles were rejected, so silence reads as coverage,
not failure.

**Narratives.** The core table. One row per narrative: statement, first seen, last seen,
7-day volume with sparkline, languages seen in, top three outlets carrying it, attribution,
stance split. Click opens the narrative: its articles, its language timeline (when did it
cross from German into French), and the fact-checks attached to it. This is the US Crisis
Tracker themes view with stance and language added.

**Sources.** Outlets as actors, from Threat Intel's actor table: outlet, tier, language,
articles this week, narratives carried, first seen. A tier filter and a co-occurrence
matrix of outlet by narrative, so an analyst can see that three alternative outlets carried
the same statement within 48 hours. That pattern is what "coordinated" looks like in this
data.

**Targets.** What is being aimed at: the upcoming votes, the parties, named people. For each
target the narratives pointed at it and their trend. Federal Councillors and party
presidents are pre-seeded as targets so the table is not empty on day one.

**Techniques.** Counts and trend per technique. Sparse for now; the value is the first
appearance of a deepfake of a named politician, which is also an alert (section 7).

**Languages.** The Swiss-specific panel. Three columns, German, French, Italian, plus
English. For each narrative, a bar per language over time. The thing to watch is the lag:
a narrative that appears in German and turns up in French a week later is being carried
across the language border, by someone. Nothing else in the product shows this.

**Calendar and timeline.** The federal election calendar seeded as `timeline_events`
scope `topic`: 27 September 2026 votes, 29 November 2026 votes, the 2027 vote Sundays, and
24 October 2027 election day. Narrative first-seen and volume spikes plotted against it,
with the escalation markers from the US Crisis Tracker. This is where "activity rises
three weeks before a vote" becomes visible.

**Responses.** A ledger of fact-checks and institutional responses extracted from the
articles: date, claim, verdict, who checked it; date, body, action. Small, but it is the
"what was done" answer to question 5.

**Insights.** The saved weekly narrative from `generate_narrative_with_llm`, same
component as the other modules, plus a one-page HTML export for sharing with a federal
body or a party, on the pattern of the Voices report export.

**Articles.** The article list with the extraction fields as filters, same component as
the other modules.

## 7. Alerts

Reuse the module alert pattern rather than a new system. Four rules, evaluated by the
monitor task after each run:

- New narrative first seen with two or more outlets in 48 hours.
- Narrative 7-day volume more than three times its previous 7-day volume, minimum five
  articles.
- Narrative seen in a second language for the first time.
- Any article with technique `deepfake` or `synthetic_text` and a target of type
  `person`.

Each alert is a `timeline_events` row and a notification through the existing bell.

## 8. Data model

Alembic prefix `sd_`.

```
sd_narratives          id, statement, name, embedding vector(768), first_seen, last_seen,
                       attribution, attribution_confidence, created_at
sd_narrative_articles  narrative_id, article_uri, stance, language, source_tier, detected_at
sd_extractions         article_uri PK, targets jsonb, techniques text[], attribution,
                       fact_check jsonb, response jsonb, language, source_tier, model, extracted_at
sd_sources             domain PK, name, tier, language, first_seen, notes
sd_targets             id, type, name, aliases text[], seeded bool
sd_daily_stats         day, narrative_id, language, stance, count
sd_schedules           same shape as geopolitical_schedules
sd_runs                same shape as policy_tracker_runs
```

`timeline_events` is reused for the calendar and alerts. The article table is not altered.

## 9. Code layout

| Piece | File |
|---|---|
| Registry entry | `app/core/modules.py`, id `swiss_disinfo`, prefix `/api/swiss-disinfo`, tab `swiss_disinfo` |
| Routes | `app/routes/swiss_disinfo_routes.py`: `/overview`, `/narratives`, `/narratives/{id}`, `/sources`, `/targets`, `/techniques`, `/languages`, `/calendar`, `/responses`, `/cooccurrence`, `/narrative` (saved insight), `/process-articles`, `/schedules*` |
| Service | `app/services/swiss_disinfo_service.py`: unprocessed-article query on the topic, `extract_with_llm`, narrative matching, stats, `generate_narrative_with_llm` |
| Monitor | `app/tasks/swiss_disinfo_monitor.py`, delay 45s, `sd_schedules` |
| Migrations | `sd_001` tables, `sd_002` seed sources, targets and calendar |
| UI | `ui/src/components/newsfeed/SwissDisinfoTab.tsx`, `SwissDisinfoTabs.tsx`, `useSwissDisinfo.ts`, `services/swissDisinfoApi.ts`; two edits in `ui/src/pages/NewsFeedPage.tsx` |

## 10. Phasing

Phase 1, the thing to look at daily: extraction, `sd_001`, Overview, Narratives, Sources,
Articles. Backfill the roughly 25 approved articles already in the topic so the tables
are not empty. About a working day for an AI including the UI build and a review pass.

Phase 2: Targets, Languages, Calendar and timeline, Responses. Half a day.

Phase 3: Alerts, weekly Insights brief with HTML export, Techniques. Half a day. Social
amplifiers through the Voices role resolution only once social collection is re-enabled
on the topic, which is a separate decision because of the noise seen on 8 to 10 September.

## 11. Open questions for the user

- Tenant: build on bugfixing and keep it there, or is this destined for a dedicated
  tenant like the Brand Watcher template? The registry gating works either way.
- Italian: the French group covers Romandie; there is no Italian keyword group. The
  firehose Swiss slice already brings Italian articles in. Add a group 24 for Italian,
  or accept Ticino as firehose-only?
- Attribution wording: the model will say "Russia" when an article says so. Should the
  dashboard show attribution as the article's claim, or only when a named institution
  (Federal Intelligence Service, EUvsDisinfo, a platform) makes it? The second is safer
  for a product a federal body might read.
- Social: back on for this topic, with the per-group platform list, or stay news-only until
  the campaign year?
