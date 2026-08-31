# Sunstar demo — oral health and whole-body health across four markets

**Date:** 2026-08-31
**Status:** Build in progress since 31 August 10:30 UK; see "Build status" at the end. The demo is Thursday 3 September, 16:30–17:00 UK.
**Source of the brief:** Oliver's email to Brendan Jennings (Sunstar) on 21 August, Gmail thread `1a02343337a50e66`, plus the follow-up on 26 August in which Brendan accepted the slot and said he would send his own questions. He has not sent them yet; the deadline we gave him is end of day Tuesday 1 September.
**Customer context:** Brendan Jennings, Sunstar (sunstar.com / sunstargum.com, Japan phone number). His role and remit are not recorded anywhere, so this spec does not assume them. HubSpot has the deal at Prospecting, €35,000, close date 31 October.

## The question the demo has to answer

"How is understanding of the relationship between oral health and wider health developing across different regional markets?"

The email commits us to comparing three perspectives:

1. What dental and medical researchers are finding.
2. What Sunstar, its competitors and other companies are saying.
3. What consumers, patients and other end users are discussing online.

And then to show four things about them: where the perspectives agree or diverge, how the discussion differs by market, which themes are gaining attention, and where commercial or public narratives are running ahead of the research.

Scope offered to Brendan, open to swaps: markets Japan, United States, Germany, France; competitors Lion, Kao, Colgate-Palmolive and P&G/Oral-B alongside Sunstar. Two example questions we offered him: the current evidence linking periodontal health to cardiovascular, metabolic and other systemic conditions; and which areas of dental research (enamel regeneration, tooth regrowth) are moving towards practical use. The email also promised a brand and adverse-media view of Sunstar and the competitors across the four markets.

Everything below exists to make those sentences demonstrable on Thursday with real collected data, not slides.

## Where to build it

Build a dedicated site, `sunstar.aunoo.ai`, and do not put this on bugfixing or pearson.

- Provision it with `scripts/provision_brand_tenant.py provision --slug sunstar --brand "Sunstar"` from the bwtemplate golden dump, then flip it to the full platform (`BW_DEDICATED_MODE=0`, `ENABLED_MODULES=*`). That is the exact path used for ibaset on 5 August and it took about four minutes of wall clock.
- Immediately rsync `app/`, `alembic/`, `static/trend-convergence` and `templates/` from bugfixing with an anchored `--exclude='/config/'`, and run `alembic upgrade head`. The template was last refreshed on 13 July and lags canonical by seven weeks; ibaset needed eight migrations after provisioning and every future clone will need the same.
- Make it Bedrock-only by copying ibaset's `litellm_config.yaml` wholesale. It was verified on 6 August to route zero aliases to OpenAI and it already carries nova-lite, nova-pro and kimi entries. Set the enrichment default to `bedrock-kimi-k2-5` in `keyword_monitor_settings`. No per-article work on a flagship model.
- Replace the template's "Generic Enterprise" org profile with a Sunstar profile built only from what we actually know (oral care manufacturer; brands GUM, Ora2, BUTLER; Japanese origin, Swiss headquarters). Leave risk tolerance, decision style and the other judgement fields NULL rather than guess.
- Check `module_config` after provisioning. On pearson a single leftover row silently disabled every module; here Brand Watcher, GeoHotSpots and ScienceWatch must be on.
- Ports 10002, 10004, 10006, 10016–10018, 10020, 10022, 10023 and 10025 are bound; let the script's `pick_port()` choose.

Reasons for a separate site rather than topics on an existing one: the brand registry has to be Sunstar-first (bugfixing's 86 brands are AI-SOC vendors), the org profile drives the framing of every generated report, and if the demo lands we hand Brendan a login to this site the same week.

## How each perspective maps to data we can collect

### Researchers

- **Semantic Scholar collector** is the backbone. It indexes the PubMed-covered dental and medical journals (Journal of Clinical Periodontology, Journal of Dental Research, Periodontology 2000, Journal of Periodontology, Oral Diseases), returns abstracts, venues and citation counts, and has years of history, which is what "how is understanding developing" needs. Add a `topic_field_mapping` entry for the new research topic → `["Medicine", "Biology"]` in `app/collectors/semantic_scholar_collector.py:19`, otherwise the field filter is skipped and generic hits come through. Two constraints found on 31 August: no tenant has a Semantic Scholar API key, a single unauthenticated request from this host already answered 429, and the collector returns an empty list on 429 without retrying (`semantic_scholar_collector.py:115-117`). And the monitor asks every collector for `page_size` results per keyword per run, which is 10 on bugfixing's settings, so the scheduled path cannot backfill five years by itself. Apply for the free API key today (approval is not instant) and write a one-off backfill script that pages `publicationDateOrYear` year by year with a sleep between calls.
- **arXiv collector** for the small amount of preprint material (oral microbiome bioinformatics, materials work on enamel).
- **RSS feeds** (`rss_feeds` table, tied to the research topic) for the journals above and for the EFP and AAP news pages. This is the cheap way to get guideline and consensus-statement news that Semantic Scholar indexes late.
- There is no PubMed collector. Semantic Scholar covers the content; say "medical literature", not "PubMed", in the demo.

### Companies

- **Brand Watch topics** created by `setup-monitoring` for each brand (one `<name> - Brand Watch` group per company) carry the news coverage of each firm.
- **Newsroom RSS** for each company's press page, registered in `rss_feeds` against the company's Brand Watch topic. This is the company's own voice, not perception of it, and it is what "what companies are saying" means. Sunstar (sunstar.com/newsroom, sunstargum.com), Lion, Kao, Colgate-Palmolive and P&G all publish feeds or feed-capable news pages; confirm each URL when registering, do not assume.
- **LinkedIn posts** via `market_collect.py` and BrightData exist on bugfixing for the AI-SOC market. They land as `bias_source = vendor:linkedin` and are the strongest "corporate voice" signal we have. Wiring them needs a `bw_markets` row and `bw_market_brands` rows. Treat that as optional for Thursday and worth doing the week after if Brendan bites; it is not what the demo depends on.

### Consumers and patients

- **xpoz collector** for Twitter/X, Reddit, Instagram and TikTok, set per group in `keyword_groups.social_platforms`. It accepts a `language` argument and ignores it (`xpoz_collector.py:246` is the only mention), so Japanese keywords are not filtered out on our side; whether xpoz returns Japanese posts is untested. X is the dominant public network in Japan, so the Japanese consumer view depends on this collector working with Japanese keywords. The key is shared with wbm and wileytest and has hit 429s before; keep the consumer topic's check interval long (daily) rather than hourly.
- **Reddit collector** (free RSS) for the English-speaking patient conversation. It turns the first term of each keyword into a subreddit slug and reads `r/<slug>/.rss` untouched, then runs a keyword search filtered to the same terms (`reddit_collector.py:104-110`). So the keywords `Dentistry`, `askdentists` and `oralhealth` pull those three subreddit feeds whole; every other keyword only reaches the search path.
- **Bluesky** as a low-volume extra.

## Topics to create

Create every topic through the Add-Topic wizard or the `save-topic` endpoint, never by inserting into `keyword_groups` alone, because the analysis step refuses to classify any topic whose ontology has an empty list and does so silently. Confirm after seeding that every topic in `config.json` has non-empty `categories`, `future_signals`, `sentiment`, `time_to_impact` and `driver_types`.

Quote every multi-word phrase in `monitored_keywords`. API-seeded keywords do not get the wizard's quoting, and the firehose treats an unquoted phrase as AND-of-words.

| # | Topic | Perspective | Collectors | Notes |
|---|-------|-------------|-----------|-------|
| T1 | Oral–Systemic Health Research | Researchers | semantic_scholar, arxiv, rss (journals, EFP, AAP) | English only; the literature is. Backfill 5 years. |
| T2-JP | Oral Health & Whole-Body Health — Japan | News and public discussion | thenewsapi (primary), newsdata | Japanese keywords, language `ja`. Measured 31 Aug: TheNewsAPI returned 111 articles for 歯周病 in the last 30 days. |
| T2-US | Oral Health & Whole-Body Health — United States | same | newsfirehose (primary), thenewsapi | English. Firehose returned 100+ for periodontitis, "gum disease heart" and "oral health" over 90 days. |
| T2-DE | Oral Health & Whole-Body Health — Germany | same | thenewsapi (primary), newsdata | German keywords, language `de`. Measured: 21 articles for Parodontitis in 30 days. |
| T2-FR | Oral Health & Whole-Body Health — France | same | thenewsapi (primary), newsdata | French keywords, language `fr`. Measured: 3 articles for parodontite in 30 days, so the thinnest market; widen the keyword list and lean on elmex/meridol brand coverage. |
| T3 | Regenerative Dentistry | Researchers plus news | semantic_scholar, arxiv, newsfirehose, thenewsapi | Brendan's second example question. |
| T4 | Oral Health — Consumer Voice | Consumers | xpoz (twitter, reddit, tiktok, instagram), reddit, bluesky | Consumer phrasing, daily check. |

### What the news collectors can actually do (checked 31 August)

- **NewsFirehose** (our own aggregator at `NEWSFIREHOSE_BASE_URL`) is English only. Its `/v1/languages` endpoint lists one language, English, with 4.25 million articles; Japanese, German and French queries return nothing. It is the right primary for T2-US and the English half of T3, and useless for the other three markets.
- **TheNewsAPI** is the only collector we have that returns Japanese, German and French press, and it does so on the `language` parameter. It is also the same account key on bugfixing, wileytest and wbm, and the collector keeps an in-process cap of 100 requests per day. Four market topics with about nine keywords each cost 36 requests per check, so run the news topics every 6–12 hours, not hourly, or the new site will burn the quota the paying customer relies on. The `.env` value is wrapped in quotes; the app's loader strips them, a hand-run curl does not.
- **NewsData** is a secondary at best. On the free plan the collector's `/news` endpoint has no date filter and only reaches back about 48 hours (comment at `newsdata_collector.py:172`), with 200 requests per day. bugfixing's `NEWSDATA_API_KEY` is empty, so the template clone will not have one either; copy wileytest's when provisioning.

One news topic per market is deliberate. It gives the market comparison for free in every existing view (filter by topic), and it is the only way to give each market its own collection language until a per-group language setting exists (see engineering, below).

### Keyword seeds

These are starting lists to be checked against the first collection pass, not final. Drop anything that pulls unrelated coverage.

**T1 research:** "periodontitis cardiovascular disease", "periodontal disease diabetes", "periodontitis atherosclerosis", "oral microbiome systemic disease", "Porphyromonas gingivalis Alzheimer", "periodontitis dementia", "periodontal disease adverse pregnancy outcomes", "oral health pneumonia elderly", "periodontitis rheumatoid arthritis", "oral-systemic health", "periodontal treatment glycemic control", "oral frailty".

**T2-US (English, also the base for translation):** "gum disease" AND "heart disease", "gum disease" AND diabetes, "oral health" AND "overall health", "oral microbiome", "periodontitis" AND "Alzheimer's", "oral health" AND dementia, "mouth-body connection", "oral health" AND pregnancy, "oral health" AND "heart health".

**T2-JP:** 歯周病 心疾患, 歯周病 糖尿病, 歯周病 認知症, 口腔ケア 全身の健康, オーラルフレイル, 口腔 全身疾患, 歯周病 動脈硬化, 誤嚥性肺炎 口腔ケア, 口腔細菌 アルツハイマー. Oral frailty (オーラルフレイル) is a distinctly Japanese public-health frame and will likely be the sharpest market difference in the whole demo.

**T2-DE:** Parodontitis Herz-Kreislauf, Parodontitis Diabetes, Mundgesundheit Allgemeingesundheit, Parodontitis Alzheimer, Parodontitis Demenz, Zahnfleischentzündung Herzinfarkt, Mundgesundheit Schwangerschaft, orales Mikrobiom.

**T2-FR:** parodontite maladie cardiovasculaire, parodontite diabète, santé bucco-dentaire santé générale, parodontite Alzheimer, maladie parodontale grossesse, microbiote buccal, santé bucco-dentaire cœur.

**T3 regenerative:** "enamel regeneration", "tooth regrowth", "tooth regeneration", "USAG-1 antibody", "Toregem Biopharma", "dental stem cells", "biomimetic enamel", "hydroxyapatite remineralization", "regenerative endodontics", 歯生え薬, 歯の再生. The Kyoto-origin tooth-regrowth drug trials are Japanese, which ties this topic back to Brendan's home market.

**T4 consumer:** "gum disease" heart, "bleeding gums" diabetes, "oral microbiome", "oil pulling", "hydroxyapatite toothpaste", "probiotic toothpaste", "mouth taping" teeth, "gum health", "receding gums", 歯周病 (for X in Japanese). The product-trend terms are there because "which themes are gaining attention" in consumer channels is a product question as much as a health one; if they swamp the topic, split them into a fifth topic.

### Ontology (shared by T1–T4, edited per topic in the wizard)

Categories: Periodontal–cardiovascular link; Periodontal–diabetes and metabolic link; Oral microbiome and neurological disease; Pregnancy and maternal health; Respiratory and aspiration pneumonia in older adults; Oral frailty and ageing; Oral cancer and HPV; Regenerative dentistry (enamel, tooth regrowth); Preventive products and health claims; Public health policy, reimbursement and screening; Clinical guidelines and professional bodies; Consumer behaviour and trends; Corporate and competitive moves.

Future signals, sentiment, time-to-impact and driver types: take the standard platform lists (the values used on the first topic of bugfixing's `config.json`). The categories are the part that has to be dental-specific; the other four lists only have to be non-empty and consistent.

## Brands to register

`bw_brands` with Sunstar primary and four peers. Keyword scoping is the whole job here; every one of these names collides with something.

| Brand | brand_keywords | product_keywords | Avoid |
|-------|----------------|------------------|-------|
| Sunstar (primary) | "Sunstar", "Sunstar Group", "Sunstar Americas", "Sunstar Europe", "Sunstar Suisse" | "GUM toothbrush", "Sunstar GUM", "G·U·M", "Ora2", "BUTLER toothbrush" | bare `GUM`; Merced Sun-Star and SunStar Philippines newspapers (both present in our caches already) |
| Lion Corporation | "Lion Corporation", "Lion Corp", ライオン株式会社 | "Systema toothbrush", "Clinica toothpaste", "Dentor Systema", "NONIO" | bare `Lion`, `Systema` alone |
| Kao Corporation | "Kao Corporation", "Kao Corp", 花王 | "PureOra", "Clear Clean", "Kao oral care" | bare `Kao` (a common surname) |
| Colgate-Palmolive | "Colgate-Palmolive", "Colgate" | "Colgate Total", "elmex", "meridol", "Colgate Optic White" | none serious; elmex/meridol carry the German and French markets |
| P&G / Oral-B | "Procter & Gamble" AND oral, "Oral-B" | "Oral-B iO", "Crest toothpaste", "blend-a-med", "Crest Pro-Health" | bare `Crest`, bare `P&G` |

Put the scoping rule in each brand's `description`, as ibaset does, so whoever edits keywords later knows why the bare name is missing. Add `news_keyword_excludes` for the two newspapers on Sunstar.

Brand Watcher's adverse-media screening, alert rules and perception view come with `setup-monitoring` and need no extra work for the demo. One gap to accept: `setup-monitoring` creates one news group per brand, and a group has one collection language, so Lion and Kao coverage in the Japanese press only arrives if their brand groups are set to `ja` (which then loses their English coverage) or if a second group per brand is added. For Thursday, leave the brand groups in English and say so. Per-brand social collection is a separate collection gap (see bugfixing's market vendors) and should not be promised as populated on Thursday.

## What the demo shows, and which existing feature shows it

No new UI is needed for Thursday. Every promised view maps to something the platform already does when the topics above have data.

| Promise in the email | Feature | Run on |
|---|---|---|
| Three perspectives, where they agree and diverge | Consensus Analysis (`/api/trend-convergence/{topic}`), exported with `consensus_html.py`; three runs side by side | T1 (research), T2-US or T2-JP (public), T4 (consumer) |
| How the discussion differs by market | The four T2 topics in the Explore dashboard, Consensus per market, GeoHotSpots map | T2-JP/US/DE/FR |
| Which themes are gaining attention | Emerging Topics detection (`/detect`) across T1–T4; Three Horizons per topic | all |
| Narratives running ahead of the research | Auspex deep-research answer to each of Brendan's questions with citations drawn from T1 versus T2/T4; Futures Cone on T3 | T1, T3, T4 |
| Brand and adverse media across markets | Brand Watcher perception, alerts, incidents | the five brands |

The one thing no existing feature does is put the three cohorts on one page for one category and score the gap between them. That is the follow-on build, not the demo:

**Perspective-gap report (after the demo, about one AI day).** Group enriched articles across T1–T4 by category and cohort, where cohort is derived from fields we already store: `news_source IN ('semantic_scholar','arXiv')` or a journal RSS = research; `bias_source LIKE 'vendor:%'` or a newsroom RSS = corporate; `social_meta IS NOT NULL` = consumer; everything else = press. For each category show attention share and sentiment per cohort, the strongest claims per cohort, and a short model-written note on where they disagree, in `CLINICAL_STYLE`. Render through `html_report_common.py` like the other exports. Analysis logic goes in a service, the renderer only renders, following the market report pattern.

### Run of show (30 minutes)

1. Two minutes: the question, the four markets, the three perspectives, on the Explore dashboard with the seven topics visible.
2. Eight minutes: the market comparison. T2-JP against T2-US on the same category (periodontal–systemic), then oral frailty as the Japan-only frame.
3. Eight minutes: research versus public narrative. Consensus Analysis on T1 next to T2-US; then the Auspex answer to the periodontal–cardiovascular question with citations from both.
4. Five minutes: regenerative dentistry (T3) with Emerging Topics and the Futures Cone.
5. Five minutes: Sunstar and the four competitors in Brand Watcher, then the leave-behinds.
6. Two minutes: what a live site would add (LinkedIn, the perspective-gap report, French depth).

Minimum data before a view goes in the show: 40 enriched articles above the relevance gate for any T2 market shown, 60 for T1, 25 for T4, and at least one Consensus run that names every category. A view under those numbers gets cut, not padded.

## Engineering that has to happen before collection

1. **Per-topic collection language and country.** Today `app/tasks/keyword_monitor.py` reads one tenant-wide `keyword_monitor_settings.language` (lines 108–132, default `en`) and passes it to every collector at line 315. With that, the Japanese, German and French topics return nothing, because NewsData and TheNewsAPI filter server-side on the language parameter. Add optional `language` and `country` columns to `keyword_groups` via Alembic, read them in the monitor with the tenant setting as fallback, and pass `country` to NewsData (the collector already accepts it, `newsdata_collector.py:106`). Expose them in the Add-Topic wizard only if time allows; setting them by SQL for four groups is fine for Thursday. About half an AI day including the migration and a collection check on each language. If this slips, the fallback is a one-off TheNewsAPI pull per language written straight into the topic by script, which gives Thursday's data but no live collection.
2. **Semantic Scholar field mapping** for T1 and T3 (fifteen minutes).
3. **Enrichment on non-English text has never been validated end to end.** The Pearson build noted the same gap for German and never closed it. Run twenty Japanese and twenty German articles through the analysis step by hand on day one and check that categories are assigned and summaries are usable. If summaries come back in the source language, add one line to the analysis prompt asking for English output and re-run those topics.
4. **Backfill.** Research via a Semantic Scholar backfill script to 2021 (see the collector note above; the scheduled monitor returns `page_size` results per keyword and no more). English news via the firehose to 90 days. Non-English news via TheNewsAPI to 30 days, in one pass, because of the shared quota. NewsAPI's free tier returns nothing and should not be flagged as a failure. Consumer topics only go back as far as xpoz allows.

## Build order and effort

Times are for an AI operator; collection wall-clock is separate and dominates.

| When | Work | Effort |
|---|---|---|
| Mon 31 Aug | Provision tenant, resync from canonical, migrate, Bedrock yaml, org profile, module_config check, per-topic language change, Scholar mapping | ~1 AI day |
| Mon 31 Aug, evening | Seed T1–T4 and the five brands, register RSS feeds, start collection, start backfills | ~2 AI hours, then wait |
| Tue 1 Sep | Check volumes per topic after the relevance gate (`topic_alignment_score >= 0.4`), prune collision keywords, validate JP/DE enrichment, run Consensus, Emerging Topics, Horizons, Brand perception; draft Auspex answers to the two example questions | ~half an AI day |
| Tue 1 Sep, evening | Fold in Brendan's questions if they arrive; if not, keep the two we offered | ~1 AI hour |
| Wed 2 Sep | Rehearse the walk-through, export the Consensus HTML and a topic report as leave-behinds, confirm every view has data | ~2 AI hours |
| Thu 3 Sep 16:30 UK | Demo | |

## Risks and open items

- **Brendan's questions.** Not received as of 31 August. The two examples in the email stand in until they arrive; if his questions need a topic we do not have, there is no time to collect for it and the answer will come from Auspex over the web, not the corpus. Say so if it happens.
- **Research leg volume.** Semantic Scholar without a key rate-limits from this host on the first call. If the key does not arrive, the research leg is whatever a throttled backfill script collects overnight plus the journal RSS feeds. Test on Monday evening, not Tuesday.
- **French is thin.** Three press articles in 30 days for parodontite. Say so on the call rather than pad it; the French view will rest on elmex/meridol brand coverage and on the research leg.
- **Japanese consumer volume.** Depends entirely on xpoz with Japanese keywords on a shared, rate-limited key. If it is thin on Tuesday, present the consumer leg on the US data and show Japan through news and oral-frailty coverage instead.
- **Non-English enrichment quality** is unproven (item 3 above). This is the most likely thing to make a market look empty when collection actually worked.
- **Collision keywords.** Lion, Kao, GUM and Crest will pull noise if anyone loosens the scoping. The first collection pass is the test.
- **Brand social tabs will be empty.** Per-brand social collection is not wired; the consumer leg lives in T4, not in Brand Watcher. Do not open the brand social tab in the demo.
- **Sunstar's own brand set per market** is a guess from public product lines. Ask Brendan which brands matter in each of the four markets; the answer changes the product_keywords, not the design.
- **Cost.** Enrichment on kimi, relevance on nova-lite, nothing per-article on Sonnet-class models. The research topic with a five-year backfill is the largest batch; run it once.
- **Case study language.** Sunstar is a prospect. Anything written for the demo says "example" or "case study", not "customer".

## Out of scope for the demo

Market Maturity Map for oral care (the vendor set is five companies, too few for the map to say anything), the perspective-gap report above, any new dashboard or page, Japanese-language UI, and LinkedIn collection via BrightData. All are reasonable week-two items if the call goes well.

## Build status (31 August, 11:00 UK)

Done today, in this order:

- `sunstar.aunoo.ai` provisioned from the bwtemplate dump (port 10019, DB `sunstar`, credentials in `/var/tmp/sunstar_credentials.txt`), flipped to full platform, resynced from bugfixing canonical, migrated to `kg_lang_001`, Bedrock-only yaml from ibaset, enrichment default `bedrock-kimi-k2-5`, `page_size` 50, Sunstar org profile as default, NewsData key and Bluesky credentials copied from wileytest/bugfixing.
- Per-group collection language and country shipped in canonical (`app/tasks/keyword_monitor.py`, `database_query_facade.py`, `database_models.py`, migration `kg_lang_001`) and on sunstar. `country` is only passed to collectors whose signature accepts it.
- Semantic Scholar: field mappings for both research topics; 429 now retries with 2s/4s/8s backoff instead of returning nothing (on sunstar after the next restart). The API key application cannot be submitted by script (HubSpot form with captcha); it needs a browser.
- Seven topics seeded through `save-topic` (groups 2–8) with the ontology above; providers, language, country, cadence and `social_platforms` set per group. Keywords are stored unquoted: TheNewsAPI treats a space as AND and quotes only narrow to exact phrases, so quoting would have cost coverage.
- Five brands (Sunstar primary, Lion, Kao, Colgate-Palmolive, P&G Oral-B) with scoped keywords and `setup-monitoring` topics (groups 9–12); newspaper excludes on Sunstar.
- RSS: EFP news on the research topic, Colgate investor releases on its brand topic. The Wiley journal feeds are behind Cloudflare and were dropped; Sunstar, Lion, Kao and P&G newsrooms publish no feed at the URLs tried.
- First collection pass started on its own within a minute of seeding. Colgate's feed had 10 articles enriched on Bedrock within ten minutes (9 above the relevance gate), which confirms the enrichment path.

Not done: the Scholar key (needs you), the Auspex/Consensus runs (need data first), the run-of-show rehearsal, and the Japanese/German enrichment check, which waits for the first TheNewsAPI pass on groups 3, 5 and 6.

### First-pass numbers (31 August, 11:15 UK)

| Group | Collected | Above the gate and enriched | Note |
|---|---|---|---|
| Research (Semantic Scholar + arXiv) | 210 | 120 | 85 from the scheduled pass, 35 recovered by `reenrich_parse_failures.py`; 17 have no abstract and cannot be enriched; all 50 arXiv hits were noise. Scholar still unauthenticated. |
| US | 324 | 34 | Firehose volume is the largest; the gate does the work. |
| Japan | 23 | 3 | TheNewsAPI on `language=ja` works; the three approved are exactly on topic (periodontal bacteria and dementia, physicians' oral-health survey, oral care after the Kumamoto earthquake). One summary came back in Japanese, so the analysis prompt now asks for English output. |
| Germany | 2 | 2 | FAZ, "how inflamed gums burden the whole body", 0.90. Two-word AND keywords were too narrow; broad single terms added. |
| France | 2 | 1 | Same fix as Germany. |
| Colgate newsroom RSS | 10 | 10 | Confirms enrichment on Bedrock. |
| Sunstar brand | 16 | 0 real | Noise only; no article about the company in 30 days. |

Also found and fixed: the keyword normaliser caps keywords at 30 characters (`MAX_KEYWORD_LENGTH`), which truncated German compounds and two research phrases; repaired by SQL. Groups 7–12 (regenerative, consumer, competitor brands) had not run when this was written; Japan, Germany and France are queued for a second pass with the widened keywords.

### After every group's first pass (31 August, 12:00 UK)

- Regenerative Dentistry 269 collected / 29 enriched; Colgate 135 / 54 (feed plus news); P&G Oral-B 55 / 17; Kao 94 / 4 (skincare, not oral); Lion 100 / 0; Sunstar 16 / 0 about the company.
- Consumer Voice collected 1,021 posts (490 Bluesky, 481 xpoz across Twitter/Reddit/Instagram/TikTok, 50 Reddit RSS) and scored none: the social evaluator defaulted to `gemma3:4b`, which this Bedrock-only site does not serve. The group's model is now `nova-lite` (also `SOCIAL_EVAL_MODEL` in `.env`) and the group is requeued.
- Lion, Kao and Sunstar are Japanese companies and their brand news is in Japanese, which is why the English brand groups found nothing usable. Added `<brand> - Brand Watch JP` groups (13–15) on TheNewsAPI/NewsData with `language=ja`, feeding the same brand topics, with Japanese brand and product keywords (サンスター, ライオン, 花王, システマ, クリニカ, ピュオーラ, オーラツー and so on).
- Reddit's search RSS answers 429 to us at the moment; only the three subreddit feeds returned posts.

### TheNewsAPI was searching titles only (found 12:10 UK, fixed)

The tenant setting `keyword_monitor_settings.search_fields` was `title,description` on every tenant, so the article body was never asked for; and the setting uses NewsAPI vocabulary, where the body is "content", a name TheNewsAPI drops silently (its fields are `title,description,keywords,main_text`). Measured over 30 days: 歯周病 8 results with the old value against 114 with the right fields, Parodontitis 4 against 23, santé bucco-dentaire 1 against 13. `app/collectors/thenewsapi_collector.py` now maps `content` to `main_text` and adds `keywords`. Fixed in canonical and propagated to wileytest and wbm the same day; sunstar's setting is now `title,description,content`. wileytest and wbm keep `title,description` until someone decides to widen it (more articles, more analysis cost). Every tenant that collects through TheNewsAPI has been searching titles and descriptions only.
