# Brand Relevance on SaaS and Monolith

Oct 6, 2026 · @Oliver Rochford

The two products decide brand relevance in different ways and share no code. The monolith labels each article's relationship to the brand and counts only independent coverage where the brand is the subject or plays a real part. SaaS attaches an article to a brand when a brand keyword is in its headline, then runs a Nova-lite yes/no check on 5 of its 11 brands. Everything below was read from the code and the live databases on 6 October 2026.

## At a glance

| Question | Monolith (brand topics) | SaaS (production) |
| --- | --- | --- |
| What decides that an article belongs to a brand | A per-brand decision: rules first, then an LLM judge, then a headline rule | The brand's keywords in the headline; then, on 5 of 11 brands, a Nova-lite score of at least 0.5 |
| Text it reads | Headline, summary and scraped text; the original-language fields too | Headline only for the keyword match |
| What it records | A label (subject, notable, sector, passing, other), whose site it is (owned, independent, unknown), the reason and the evidence | Accept, reject or review per article and brand, plus a score; rejects are not stored as links |
| Same-name companies | Profile rules: names that need context, words that mark a different company, collision phrases | Per-brand exclude and required keyword lists; the LLM prompt also mentions namesakes |
| The brand's own sites | Counted as owned, never as press | Not distinguished |
| Deal listings, valuation pages | Deal listings count, marked promotional; valuation pages excluded | Not handled |
| Social posts | Not judged by this path; a separate social evaluator handles them | Come in through official sources, attached with no relevance check |
| When the model fails | Unavailable: not counted, retried up to three times | Review: kept, re-scored on the next hourly run |
| Switch | `BRAND_RELATION_DECISIONS` per site; on at 7 running sites | Per-brand config; gate on brands 1 to 5 |
| Market Monitor vendors | Same decision gates vendor links, behind `MARKET_VENDOR_DECISIONS`; on at panaya only | Market code exists only in the development tree, off, with no relevance check |

## Monolith: how a brand article is decided

A brand topic is a keyword group named "Brand Monitoring X" or "X - Brand Watch". When the collector brings in a news article for one, the ingest service calls the brand path before anything else (`brand_ingest_hooks.pre_decide`). The decision (`brand_decision.decide`) runs these steps and stops at the first that settles it:

1. **Profile.** The brand's names, products, original-language names, own websites and same-name rules come from its `bw_brands` row and the vendor registry (`brand_profile.build_profile`). A brand topic with no profile returns no decision, and the article goes down the site's older path. A configuration error, such as two brands claiming the same topic, defers the article.
2. **Exclusions.** A page on a site listed as never the brand's press, or an automated valuation page ("CL DCF Analysis: Intrinsic Value..."), is "other" with no model call. Deal listings are not excluded: they are marked promotional and go on (your 6 October decision).
3. **Whose site.** The page is owned if it sits on one of the brand's own domains, independent if it has any other publisher, unknown if it has none (`source_relation`).
4. **Mention.** The brand must be named in the article's own text, not just in the collector's claim. Names that need context, and words that mark a different company with the same name (SunStar the Philippine newspaper, Colgate University), are applied here. A listed fan or recipe site that names the brand is settled as a fan page.
5. **Reuse.** If the same article and brand were decided before under the same inputs, that decision is reused and no model is called.
6. **No mention.** An article that does not name the brand goes to the site's existing topic rules: relevant becomes "sector", not relevant becomes "other".
7. **Judge.** An article that names the brand goes to the LLM judge. The model is `BRAND_JUDGE_MODEL` if set, else `HYBRID_RELEVANCE_LLM_MODEL`, else Nova-lite; no running site sets either, so every site uses Nova-lite today. `BRAND_JUDGE_FALLBACK_MODEL` adds a second LLM route if the first fails, and `BRAND_JUDGE_ROUTE=jev` swaps the first route for Jev. It must answer with one label and a one-sentence reason in strict JSON, or the answer is treated as unavailable. The rubric is version brand-judge-3.
8. **Headline rule.** If the brand is in the headline and the judge said sector or passing, or gave no answer, the label is raised to notable. A judge's "other" is kept, because it means the judge read the headline name as a different company or the story as unrelated (policy version brand-coverage-3; the spec's Appendix C records the change).
9. **Unknown publisher.** A subject or notable label from a page with no readable publisher is deferred, not counted.

The article counts as earned coverage only when the label is subject or notable and the site is independent. Sector stories and the brand's own content are kept and shown but never counted as press. Passing mentions and "other" are stored as rejections.

**Where it is stored.** One row per article and brand topic in `keyword_article_matches`: `brand_relation`, `source_relation`, `judge_version`, `decision_evidence` (matched name, extract, reason, model, rubric) and `last_failure` (migration br\_001).

**When the model fails.** The row is stored as unavailable with the reason and an attempt count. It is not counted. It is retried up to three times, by the enrichment sweep on sites that have one and by a 30-minute cron on the others (`brand_retry`). The judge is capped at 600 calls an hour.

**Who reads it.** Brand Watcher's earned-news filter, its classification pass, the risk assessment and the alert and digest queries all use the label: an article whose label says it is not earned coverage of that brand is left out (`brand_coverage.label_veto_sql`, `earned_news_scoped_sql`, `alert_earned_sql`). Articles decided before labels existed keep their old verdicts; nothing is rescored automatically. The Articles tab shows a coverage breakdown per brand (`GET /api/brand-watcher/brands/{id}/coverage-split`).

**Measured on Sunstar** against your labels on 82 articles: precision 0.93, recall 0.65 on your raw answers; precision 0.86, recall 1.00 with your three policy answers applied, and 1.00 precision once all single-brand listings count. Oviva, 74 articles: precision 0.83 (old path 0.25), recall 0.38, with 7 of the 8 misses being the recipe sites now kept as fan pages.

## Monolith: Market Monitor vendor links

With `MARKET_VENDOR_DECISIONS` on, a vendor is credited with a news article only when the same brand decision rates it earned coverage. Today that is panaya only.

The market's name match (`market_corpus.attribute_vendors`) still finds a vendor's reviewed names in the headline and summary and still applies the market context check. The decision then runs for each news article and vendor pair (`market_vendor_decisions`):

- **Earned:** the vendor link and the entity link are written together.
- **Owned, sector, passing, other, fan page:** no vendor link. Pages on the vendor's own site are still linked as owned by the separate owned-page pass.
- **Unavailable:** no link yet; retried under the same three-attempt cap, then linked if earned.
- **Every outcome:** the article still enters the market corpus, and the decision is stored, one row per article and vendor, in `brand_article_decisions` (migration bm\_001).

Social posts keep the old rule: they are linked by name match alone. Vendors' own LinkedIn posts are attributed by the account they come from, as before. The market report's change panels wait for the later of the collection start and the switch-on date (`config.vendor_decisions_since`), so a fall caused by the stricter rule is not reported as lost coverage; on panaya, comparisons resume on 5 December 2026. Existing links were left as they were.

| Market | News links audited | Kept as earned | Vendor's own site | Dropped | Social links (old rule) |
| --- | --- | --- | --- | --- | --- |
| panaya, Enterprise Test Automation | 111 | 22 | 86 | 3 | 105 |
| Sunstar, Oral Care (flag off) | 10 | 10 | 0 | 0 | 317 |

The three panaya drops are two UiPath false matches on its generic product names ("Test Suite", "Test Manager") and one valuation page; those product names now count only with "UiPath" nearby. Sunstar's vendor links are almost all social (Instagram 156, Bluesky 60, Twitter 55, TikTok 40, Reddit 6), which this rule does not touch.

## Monolith: where it is switched on

The brand decision is on at seven of the eight running monolith sites. It is off on bugfixing, where `BRAND_RELATION_DECISIONS` is not set in `.env` (checked 7 October). Only Sunstar and wbm had stored decisions when this table was made on 6 October: the other sites had not collected a new brand article since their switch-on, or have no brand topics.

| Site | Brand decision | Market vendor decision | Retries by | Stored brand decisions | Note |
| --- | --- | --- | --- | --- | --- |
| Sunstar | on | off | cron | 145 | live since 12:05 |
| Oviva | on | off | cron | 0 | WeightWatchers recipe sites kept as fan pages |
| abm | on | off | enrichment sweep | 0 |  |
| wbm | on | off | cron | 4 | four "sage" rows decided not coverage after the threshold fix |
| wileytest | on | off | cron | 0 | restarted onto the flag at 23:12 on 6 October |
| panaya | on | on | cron | 0 | no brand topics; vendors come through the market |
| wiley | on | off | cron | 0 | no brands |
| bugfixing | off | off | enrichment sweep | 0 | canonical tree |
| bwtemplate | on, site stopped | off | none yet | 0 | new clones inherit the flag |

Turning a flag off and restarting the site restores the earlier behaviour: readers fall back to the old rules and the ingest path stops deciding.

## SaaS: how brands get their articles

On SaaS an article belongs to a brand once a row exists for it in `bm_article_categories`. Production has 11 brands, all enabled, and 3,199 article and brand pairs. Two paths write those rows.

**Main path: hourly classification** (`run_classification`, only for customers with the brand monitoring feature):

1. **Headline keyword match.** A case-insensitive whole-word match on the headline only, never the summary or body, against the brand's name, slug, brand keywords, product keywords and people keywords. The code says why: for Wiley, matching summaries pulled in 628 articles, mostly science news citing a Wiley journal; headlines gave 32. Optional required words must also appear in the headline; exclude words veto it. It searches the whole shared article store, up to 2,000 candidates a run.
2. **E5 similarity gate,** opt-in per brand. Off for every production brand.
3. **Relevance gate,** opt-in per brand. On for brands 1 to 5 (aunoo-ai, dataminr, inoreader, feedly, palantir) in LLM-only mode: Nova-lite scores each candidate from 0 to 1 (1 = the brand is central, about 0.5 = secondary, 0 = off-topic or a namesake), and a score below 0.5 rejects it. Brands 8, 10, 11, 15, 16 and 17 (picus-security, sage-group, blackbird-ai, itc, ammune-ai, oviva) have no gate: the headline match alone decides.
4. **Category.** Almost every kept article gets at least one of 11 categories; this is not a gate.

Decisions are recorded since 5 October 2026 in `relevance_evaluations`, `relevance_decisions` and `relevance_latest`. Production holds 30 accepts, 101 rejects and 2,017 rows with no action. A rejected article is simply not linked. If the model fails or answers badly, the decision is "review", and review articles are kept and re-scored next hour: the gate fails open. If the whole gate errors, every candidate is kept. A person can accept or reject an article by hand, and that overrides the model.

**Second path: official sources.** For sources a brand has opted into (Bluesky, Reddit, SEC EDGAR, OpenAlex, Crossref and others), the poller searches with the brand keywords and links the results directly, with no headline match and no relevance gate. Bluesky, OpenAlex and Crossref results must contain a brand term as a whole word; Reddit trusts posts from the brand's own subreddit. This is where most social posts come from (feedly: 400 Bluesky and 69 Reddit rows against 12 that passed the gate; sage-group: 1,002 SEC EDGAR and 109 Bluesky).

**What SaaS does not have:** no subject or passing label in what customers see, no owned versus independent split, no deal-listing or valuation-page rule, no headline rule. A Jev shadow model (`TYPESAFE_SHADOW_RELEVANCE=1`) labels some candidates as central, secondary, incidental or off-topic, but only records its answers (46 off-topic, 4 incidental so far) and changes nothing.

**Who reads it.** The brand pages, statistics, share of voice, sentiment, alerts and the MCP tools `get_brand_articles` and `get_brand_sentiment_and_alerts` count the linked rows. The competitive landscape, competitor timelines, people mentions and "articles by term" run their own headline regex with no gate, so `get_brand_coverage` combines a gated count and an ungated one.

## SaaS: how topics get their articles

Topics work separately from brands. Five routes put articles into the shared `articles` store. Three of them attach a topic directly (analyst publish, RSS collection and the brand official-sources poller), and an LLM tagger adds topics to the rest. The two largest are the analyst publish step and, until 9 September, the firehose import.

- **Analyst publish.** The analyst pipeline (described below) copies its confirmed articles into `articles` with the topic attached (`app/analyst/publishing.py`). It is the largest topic feeder today, at about 16,300 new rows in the week to 7 October. An article whose URL already exists only gains the topic id. Publishing never runs in reverse: rejecting an already-published article in the analyst UI does not remove its topic.
- **Firehose import.** An hourly job copies NewsFirehose articles from its database straight into `articles` (`scripts/import_firehose_corpus.py`, `saas-firehose-import.timer`). It attaches **no topic** and no relevance score; those rows reach a topic only if the topic tagger below tags them, and 88% never were. It added 24,000 to 29,000 articles a day until 9 September 2026. Since then it adds none, because `FIREHOSE_DSN` is not set on production and the importer still reads the old, frozen local copy.
- **Collection.** Every 15 minutes each active topic is collected. NewsAPI is configured but its key is empty in production, so production collects topics through RSS. There is no relevance check at collection: the article simply gets the topic's id added to `articles.topic_ids`.
- **Topic tagging.** An LLM (Llama 3.3 70B in production) tags untagged articles with the curated topics they are "genuinely about, not topics it mentions in passing". It runs at ingest and as a background loop. The loop is currently stuck: it re-sends the same 50 articles every 5 minutes.
- **Relevance score.** Every 5 minutes a backfill scores tagged articles against each of their topics with Nova-lite and writes the highest score into `articles.relevance_score`. The score is not tied to one topic and no decision follows from it; a low score never removes a topic tag. On failure the score stays empty and is retried later.

The analyst topics run their own pipeline: a small embedding model scores each article (the DeBERTa model is not present in production, so it runs on MiniLM alone), Nova-lite settles the uncertain middle band, and articles are bucketed confirmed, pending or rejected around each topic's threshold. Only confirmed articles are published, and a publish also needs the article's alignment score at or above the threshold, at least 10 eligible articles for the topic, a run with no errors and at least 95% scoring coverage, and a per-article validation pass. In the last 30 days that was 90,832 confirmed, 220,957 rejected (131,549 on the embedding score alone) and 16,690 pending.

**Who reads it.** The reader feed and the public topic pages show articles with `relevance_score` of at least 0.3. The newsletter takes any scored article. The MCP tool `get_topic_articles` filters on the topic tag and dates only, with no relevance filter; the semantic search tools add vector distance. Social posts are scored the same way as news on this path.

## Differences that matter

1. **A model failure keeps the article on SaaS and holds it back on the monolith.** SaaS treats a failed or malformed answer as "review" and keeps the article; the monolith stores it as unavailable, leaves it out of every count and retries it. During a model outage SaaS brand counts rise with unchecked articles; monolith counts pause.
2. **Six of SaaS's 11 brands have no relevance check at all,** Oviva among them: a brand keyword in the headline is enough. The monolith checks every brand article that names the brand.
3. **SaaS reads only the headline for brands.** A story about the brand whose headline does not name it is never found; one that names it in passing in the headline is kept unless the brand has the gate. The monolith reads headline and text, and only a headline mention is lifted to coverage automatically.
4. **SaaS does not separate the brand's own content from press.** Official-source results (Bluesky posts, Reddit threads, SEC filings) are linked with no check and counted alongside press, and nothing marks which ones the brand published itself. The monolith keeps them as owned and never counts them as press.
5. **SaaS mixes gated and ungated counts.** Brand statistics count gated links; the competitive landscape counts headline matches with no gate; the MCP coverage tool returns both side by side.
6. **Social posts:** on SaaS they enter brands through official sources unchecked and are scored like news on topics; on the monolith a separate social evaluator judges them, and the brand decision covers news only.
7. **No shared code.** None of the monolith's brand decision code exists in either SaaS tree, and SaaS's relevance code is the same in production and the development tree. The development tree's Market Monitor attributes vendor posts with no relevance check, is switched off, and its vendor tables are empty.

## Sources

Monolith, canonical tree `/home/orochford/tenants/bugfixing.aunoo.ai` (commit 7e74f4e6 and later):

- Decision: `app/services/brand_decision.py` (`decide` line 356; exclusions 381, mention 397, reuse 418, judge 443, headline rule 459; judge route `configured_judges` 316 to 327; earned and admitted 86 to 97)
- Profile and mention rules: `app/services/brand_profile.py` (`build_profile` 220, `detect_mention` 411, `source_relation` 488, `exclusion` 531, `fan_site_reason` 549, `promotional_reason` 562)
- Ingest hooks: `app/services/brand_ingest_hooks.py` (`pre_decide`, hourly cap at line 40)
- Readers: `app/services/brand_coverage.py` (`label_veto_sql` 91, `earned_news_scoped_sql` 131, `alert_earned_sql` 149, `coverage_split` 179); `app/routes/brand_watcher_routes.py` lines 33 and 2550; `app/tasks/brand_watcher_monitor.py` and `app/services/bw_digest_service.py`
- Social posts kept out of the news pipeline: `app/tasks/keyword_monitor.py` around line 913; `app/services/social_eval_service.py`
- Retries: `app/services/brand_retry.py`; `app/tasks/enrichment_retry_sweep.py` line 207
- Market vendors: `app/services/market_vendor_decisions.py`; `app/services/market_corpus.py` (`attribute_vendors`, `write_vendor_link`); `app/services/market_analysis.py` (`comparison_baseline`)
- Specs: `docs/BRAND_RELEVANCE_SPEC.md` (progress log in Appendix C), `docs/BRAND_RELEVANCE_MARKET_VENDORS.md`
- Live state: each site's settings file, the root crontab and each site's database, read on 6 October

SaaS production, `/home/orochford/tenants/saas.aunoo.ai`, database `aunoo_saas_prod`:

- Brand path: `app/features/brand_monitoring/service.py` (headline-only match 100 to 154, gates 591 to 614, review kept at 400, readers 1003 to 1999); `app/relevance/scorer.py` (LLM prompt 293 to 321, failure handling 343 to 364); `app/relevance/decision.py`
- Official sources: `app/tasks/official_sources_poll_task.py`; `app/collectors/reddit.py`
- Topics: `app/analyst/publishing.py` (analyst publish); `scripts/import_firehose_corpus.py` (firehose import); `app/tasks/collector_task.py`; `app/topics/classifier.py`; `app/relevance/backfill.py`; `app/analyst/pipeline/steps/score_relevance.py`; `app/analyst/pipeline/runner.py` 263 to 273
- MCP tools: `app/auspex/brand_tools.py`; `app/auspex/tools.py`
- Settings: `bm_brands.config` per brand; `ai_model_configs`; worker drop-ins in `/etc/systemd/system/saas-worker.service.d/`; production `.env`
- Development tree compared: `/home/orochford/tenants/bugfixing.aunoo.ai/saasmvp-app`
