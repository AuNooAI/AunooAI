# Proof-of-Value runbook: Panaya, Sunstar, Oviva

_Written 2026-10-05. State checked live on the four tenant databases, the shared alert mailbox and HubSpot that morning._

## What this is

Three prospects are in a proof of value (HubSpot stage "Pilot / PoV" for Sunstar and Oviva, "Engagement" for Panaya, each at EUR 35,000). The product they are buying is the daily service Wiley gets from the wileytest site: one reviewed briefing every weekday plus observer alerts, all passed through a human before the customer sees them.

This runbook says how that daily service works on wileytest, what each prospect site has today, what is missing, and the daily and weekly checklist for running all three the same way.

## The reference: how the Wiley daily service runs

Everything below is what actually happens on wileytest, not the design.

**Nothing reaches the customer automatically.** The platform sends every email to an internal mailbox, `wiley@aunoo.ai` (it lands in Oliver's aunoo.ai inbox) with Ryan copied. Oliver reads, picks, and forwards to the three Wiley contacts (Pascal Hetzscholdt and two colleagues, gtiurina and agalli at wiley.com) from his own address, usually between 08:00 and 09:10 UTC. On 2026-10-05 he forwarded the briefing, the Scientific Publishing Watcher report and the Competitor Tracking report. The geopolitical and AGI observers stayed internal.

**The morning sequence, Berlin time:**

| When | What | Who |
|---|---|---|
| 03:30 to 10:00 | Seven observers run on their schedules and email the internal mailbox | scheduler |
| 09:00 to 10:30 | Open Briefing Desk, "Compose today's briefing", model `claude-sonnet-4-5` | operator |
| after compose | Read the draft. Target is 8 articles, 7 incidents, 5 emerging topics. Cut what is wrong, add what is missing | operator |
| then | Finalize. The reviewer gate runs: a deterministic check of every date, figure and brand name against the sources, then a judge, then up to three repair rounds | platform |
| then | Share via Email to the internal mailbox | operator |
| by ~10:20 | Forward the briefing and the observer reports worth sending to the customer contacts, Ryan in copy | Oliver |

Compose times over the last 60 days cluster at 09:00 to 10:59 Berlin. Briefings go out Monday to Friday only, four or five a week. 146 briefings have been finalized since 29 January.

**The reviewer gate matters.** Of the 15 briefings reviewed in the last 30 days, 3 were approved clean, 9 approved with warnings, and 3 sent back for revision. A revision means the operator regenerates or clicks "Finalize anyway" with a written note. Do not skip this on a prospect site: the fabricated dates and invented years it catches are exactly what loses a pilot.

**The wileytest observer set** (all daily or every 24 hours, chunked search, report generated, email to the internal mailbox):

| Observer | Lookback | Alerts last 30 days | Forwarded to customer? |
|---|---|---|---|
| Scientific Publishing Watcher (10:00) | 3 days | 2,011 | yes |
| Competitor Tracking (every 24 h) | 3 days | 1,017 | yes |
| AI & Content Licensing Models (every 24 h) | 3 days | 58 | sometimes |
| Emerging Geopolitical Signals (08:00) | 3 days | 7,314 | no |
| Attention-Maximizing Geopolitical Leader Simulator (09:00) | 3 days | 1,972 | no |
| Early indications of AGI (every 24 h) | 3 days | 1,715 | no |
| Negative Social Sentinel — Wiley (08:00) | 14 days | 19 | no |

The pattern to copy is three roles: a domain watcher written from the customer's point of view (the Scientific Publishing Watcher instruction is the model: who the reader is, what counts, what to ignore, "be conservative"), a competitor tracker that only fires on named competitors, and a reputation or adverse-media monitor. The geopolitical ones are Wiley-specific extras.

**What it costs.** wileytest spends about USD 18 a day on language models in total, most of it on article enrichment and emerging-topic validation, not on the briefing. A compose is about USD 0.14 on Sonnet and a finalize is two or three Sonnet review calls plus a repair or two. The prospect sites are far cheaper: Sunstar USD 1.19 a day, Panaya USD 0.95, Oviva USD 0.27 (7-day averages).

## Where each prospect site stands today

### Panaya (panaya.aunoo.ai, port 10027, database `panaya`)

Deal: "Panaya - Intelligence Retainer", stage Engagement, close date 31 October. Contact Amos Bergerbest Eilon. The product-team colleague he promised to introduce has not been named yet, so there is nobody to forward to.

What is running:

- One market topic, "Market Monitoring Enterprise Test Automation", fed by a news group, a social group and a Bluesky vendor group. Six vendors only (Panaya plus Tricentis, smartShift, Nova Intelligence, Worksoft, UiPath's testing line). Do not re-add the dropped peer tier.
- Two observers, both kimi, emailing oliver.rochford@aunoo.ai with a report: "Adverse Media Monitor — Enterprise Testing" at 08:00 (14-day lookback, 29 alerts in 30 days) and "Competitor Activity — Enterprise Testing" at 08:30 (7-day lookback, 73 alerts). Both succeeded today. Their instructions and report prompts are already written from Panaya's point of view and are the best of the three sites.
- Briefing Desk: the topic list was set today at 13:03 (that one topic) and the first draft briefing was composed today (8 articles, 7 incidents, 3 emerging topics). The reviewer code and judge prompt are present. The compose model is pinned to `bedrock-kimi-k2-5`.

Done on 5 October (afternoon):

- Compose model pinned to `claude-sonnet-4-5`. On wileytest the kimi curator kept re-picking generic commentary and ignoring "one item per development"; Sonnet fixed it on 16 September.
- Both observers now email the internal mailbox and Ryan, like every other site.
- A third observer, "Enterprise Application Change — Demand Signals" (daily 08:15, 3-day lookback, kimi, report on), watches platform-vendor moves, enterprise transformation programmes, system-integrator moves and agentic-testing category signals. It ignores testing-vendor news, which the competitor observer owns.
- The briefing service, routes, compose service and judge prompt were refreshed from canonical and the service restarted.
- Future social follows are scoped to testing terms (`bw_markets.config.follow_markers` on market 1312).

Still open:

1. Customer recipients. None until Amos names the product-team contact.
2. A one-topic briefing will be thin. The emerging-topics detector on this site is set to a minimum of 50 articles, and one market produces far fewer new items a day than Wiley's 18 topics. Check the daily article count before promising a daily briefing; three a week may be the honest cadence for this market.
3. Stray tweets. The site was cloned from bugfixing with its 1,114-row social follow list, and 322 posts by a security analyst (@anton_chuvakin) landed under the topic "Enterprise Test Automation" between 21 September and 5 October because the default follow markers are AI-SOC words. The follow list reads as empty now (0 watchlisted), but the 322 rows are still in `articles` and `bw_market_articles` for market 1312 and will show in the market's social views until deleted. Deleting them was blocked for the agent; run it by hand if wanted:

```sql
DELETE FROM bw_market_articles WHERE market_id = 1312 AND article_uri IN
  (SELECT uri FROM articles WHERE topic = 'Enterprise Test Automation' AND social_meta->>'followed' = 'true');
DELETE FROM articles WHERE topic = 'Enterprise Test Automation' AND social_meta->>'followed' = 'true';
```

### Sunstar (sunstar.aunoo.ai, port 10019, database `sunstar`)

Deal: "Sunstar - Intelligence Retainer", stage Pilot / PoV, close date 31 October. Contact Brendan Jennings. The brief is his two questions of 1 September: where the oral-systemic narrative has whitespace across science, competitors, professionals and consumers, and which themes are gaining momentum.

What is running:

- 22 keyword groups: Sunstar and four competitor brand watches (English and Japanese), research, consumer social, and press groups for Japan, the United States, Germany, France, Italy, Spain and Brazil. Kao's groups and the United Kingdom press group are switched off on purpose.
- The briefing topic list has 11 topics: the Sunstar brand, research, the four original country press topics and the four competitor brands. The Italy, Spain and Brazil press topics are collected but are not in the briefing list.
- Three observers, daily at 06:40, 06:50 and 07:00 with a 2-day lookback and reports on: "Evidence Watch - claims ahead of the science" (59 alerts in 30 days), "Competitor moves on oral-systemic health" (60), "Sunstar adverse media and reputation" (1, and low volume is expected). Report prompts name the audience ("Sunstar's scientific communications and brand teams") and are the model for the other sites.
- Reviewer gate present; three briefings carry a review record.

Done on 5 October (afternoon):

- Compose model pinned to `claude-sonnet-4-5`. This pin also drives the emerging-topics detector, which runs every 24 hours here, so watch the weekly spend line.
- All three observers now run on `bedrock-kimi-k2-5` explicitly, with chunked search and a 300-article ceiling, and email the internal mailbox and Ryan only. The gmail address is gone.
- A fourth observer, "Professional and policy momentum on oral-systemic health" (daily 06:55, 2-day lookback), watches associations, ministries, insurers and clinical bodies, Japan first. It is Brendan's second question (which themes gain momentum) read from the institutional side.
- The briefing topic list now has 14 topics: Italy, Spain, Brazil and Regenerative Dentistry were added.
- The briefing service, routes, compose service, ranking helper and judge prompt were refreshed from canonical and the service restarted. A draft briefing for 5 October was composed from the service layer to restart the routine; it is waiting in Briefing Desk.

Still open:

1. Nothing has been forwarded to Brendan from the shared mailbox in the last 30 days. The routine restarts with today's draft.
2. **The Japanese press topic approves almost nothing, and that is supply, not a scoring bug.** In the last seven days 181 articles arrived for "Oral Health & Whole-Body Health - Japan" and 0 were approved; Germany 1 of 50, France 0 of 19, Italy 0 of 21, the US 21 of 106. We measured it on 5 October rather than guessing:
   - TheNewsAPI searches article bodies for these groups (the collector maps the "content" field to the provider's main_text). For Japanese that index returns phantom matches: we fetched all 181 pages, and 111 of them (61%) do not contain the search term anywhere. Those are the TV listings, pet stories and pension advice. The other 52 body-only rows are genuine mentions, and the on-topic items are among them, so body search must stay. Germany has no phantom problem: all 50 pages carry the term; its low approval is the judge being strict with dental lifestyle pieces. The gate rejects the phantoms correctly, at nova-lite cost, so they are noise in the counts rather than money. A guard for CJK-language groups is live on sunstar and in canonical since 5 October 16:05 (keyword_monitor.py, `_page_carries_tokens`): when a new TheNewsAPI result lacks every word of the matched keyword in its title and summary, the page is fetched once and the article is dropped if the words are not on it. A failed fetch keeps the article, so the gate still sees it. Checked against this week's rows: 66 of the 111 phantoms would be dropped, 38 kept because the fetch failed, 7 uncertain; every phantom tested came back as a drop or a keep-on-failure, never a false keep of the term. The log line to look for is "Dropped N of M TheNewsAPI results for '<keyword>' (ja)".
   - Re-scoring all 377 rows with the newer scorer that reads the topic definition changed nothing (Japan 1 of 181 either way). Re-judging the 28 best Japanese rows with Kimi instead of nova-lite agreed with nova-lite on every row but one. The only genuinely on-topic Japanese item of the week, an Osaka University series on "oral comprehensive power", passes under Kimi (0.65) and sits at 0.5 under nova-lite. A second, on healthy life expectancy and oral function, scores 0.4 under both judges and misses the 0.45 gate.
   - A title-and-description-only search for 歯周病 (periodontitis) over seven days returns one article. Japanese press on the oral-systemic link is one to three items a week on this provider, and body search is what finds them, so turning it off would lose the good ones too.
   - NewsData, the second provider on every non-English group, runs out of daily credits partway through each day: about 240 successful calls a day, then "exceeded your assigned API credits" (202 such failures on Sunstar since 1 October). The key is shared with oviva, wileytest and wbm, so all four sites draw on the same daily allowance. Groups that run late in the day get nothing from it.

   What would raise the yield: restore NewsData credits; add Japanese dental and health outlets as RSS feeds (the `rss_feeds` table on this site holds EFP and Colgate IR today); lower `min_relevance_threshold` to 0.4 on the six press groups, which admits the 0.4-scored items (two in Japan this week, one in the US) at the cost of a little more noise. No change to the scorer is warranted.

### Oviva (oviva.aunoo.ai, port 10026, database `oviva`, dedicated Brand Watcher mode)

Deal: "Oviva - Intelligence Retainer (Free Pilot)", stage Pilot / PoV, close date 30 November. Five contacts receive forwards: Kinjal Shah, Carlota Gorosabel, Jana Dallmann, Melanie Schwendimann, Paul Gruber.

What is running, and this one is already a live daily service:

- The Brand Watcher adverse-media digest goes to the internal mailbox at about 06:05 UTC every day. Oliver forwards it to the five Oviva contacts (today at 09:03 UTC, Ryan and Alvaro in copy).
- Observer "Adverse Media Monitor — Oviva" at 08:00, kimi, 14-day lookback, report on, to the internal mailbox (18 alerts in 30 days).
- Observer "Competitor Monitoring", every 24 hours, 7-day lookback, no report, emails **kinjal.shah@oviva.com directly**. It runs on `claude-opus-5`. This is the only path on any of the three sites where the platform writes to a prospect without a human in between.
- 22 keyword groups: Oviva plus nine competitors in English, German groups for Oviva, HelloBetter and Zanadio, and social groups.

Done on 5 October (afternoon):

- The Competitor Monitoring observer runs on `bedrock-kimi-k2-5` instead of Opus, generates a report with an audience line, runs daily at 08:30, and emails the internal mailbox and Ryan. Kinjal Shah no longer receives it directly; everything now goes through the same human forward as the digest. Reverting that is one update to `signal_instructions.config.email_recipient` on row 3.
- A third observer, "GLP-1 access, policy and evidence watch" (daily 08:15, 3-day lookback), watches NHS, NICE, BfArM DiGA, Swiss reimbursement, supply and price, provider regulation (MHRA, CQC, GPhC, ASA) and major evidence. It sees only what the brand keyword groups collect, so it catches policy items that name Oviva or a competitor, not the whole policy stream.
- Briefing Desk exists now. The dedicated-mode tab list gained `briefing-desk` (canonical change in NewsFeedPage.tsx, built from a clean checkout without the Swiss module and deployed to oviva only), the reviewer service, routes, compose service, ranking helper, the judge prompt and the one facade method it needed were copied from canonical, the topic list is the Oviva brand plus eight competitors, the compose model is `claude-sonnet-4-5`, and the service was restarted. A first draft was composed from the service layer.

Still open:

1. The news pool is thin. In the last seven days the Oviva brand topics together produced about 27 enriched news articles and roughly 600 social posts, and the briefing excludes social posts. Expect four or five articles a day at best. Use the briefing when there is something to say, not daily; the digest and the observers remain the daily service.

## Bringing a site up to the wileytest standard

Do these in order. Each has a check.

1. **Org profile.** One default row with a real description. All three have it (Panaya id 10, Sunstar id 8, Oviva id 8). The briefing synthesis uses the full profile block.
2. **Briefing topic list.** `emerging_topics_settings.daily_briefing_topics` must include the own-brand topic (the shortlist reserves five slots for it) and every topic the customer should see. Set it by SQL or the checkbox list in Briefing Desk.
3. **Compose model.** `emerging_topics_settings.model = 'claude-sonnet-4-5'`. The page dropdown overrides it per compose, but the pin is what a tired operator gets.
4. **Reviewer gate.** `grep -c _run_review app/services/daily_report_service.py` must be nonzero and `data/auspex/agents/dr_reviewer_agent.md` must exist. The judge prompt loads at startup, so edits need a restart.
5. **Observers.** Two to four per site: adverse media, competitor, one domain watcher written for the customer's reader. Settings that work: daily schedule before 08:00 Berlin, chunked strategy, `max_articles` 300, `generate_report` true with a report prompt that names the audience, model `bedrock-kimi-k2-5`, email to the internal mailbox only. Lookback 1 to 3 days for a daily run. Panaya and Oviva run 14 days and are safe only because the sent ledger drops anything already alerted.
6. **Recipients.** Internal mailbox plus Ryan. Customer addresses only when the customer has asked for direct delivery and the observer has a report prompt.
7. **Dry run.** Trigger each observer by hand (`run_agent_now(db, id)` after loading the tenant .env; it will email if anything clears the threshold), compose one briefing, read the review verdict, share it to yourself.
8. **Monitoring.** Each tenant needs a blackbox probe in /opt/monitoring. All three have one (checked today).

## Daily checklist per site (weekdays, Berlin time)

| Time | Step | Good looks like | If not |
|---|---|---|---|
| 08:15 | Observer emails are in the internal mailbox | One email per scheduled observer with a report section, not just a list | `last_run_status` and `last_run_error` on `signal_instructions`; an email with articles and no analysis is the Bedrock empty-response case, which retries three times then falls back |
| 08:30 | Collection ran overnight | New articles today for the briefing topics | Check `keyword_groups` last run and the topic's label list; an empty label list means enrichment silently does nothing |
| 09:00 | Compose | 8 / 7 / 5; every topic with material has at least one slot. Takes about a minute per topic because emerging-topic detection runs per topic (Oviva 9 topics about 3 minutes, Sunstar 14 topics about 11 minutes) | A high "backfilled" count in the compose log means the pool was thin, not the code (Sunstar 6 of 8 and Oviva 7 of 8 on 5 October). Say so in the cover note rather than padding |
| 09:20 | Edit | Cut duplicates and off-topic picks, fix a theme title if needed | Edited themes share correctly; the 17 September fix is on all three sites |
| 09:30 | Finalize | approved or approved_with_warnings | revision_requested: regenerate once; if it comes back again, read the findings, fix the sentence, "Finalize anyway" with a note |
| 09:45 | Share to the internal mailbox | Email arrives with summary, themes, incidents, emerging topics, articles | Share failures show the raw error; it is almost always a recipient typo |
| 10:00 | Forward to the customer | Briefing plus the one or two observer reports worth their time, two-line cover note on what changed | Skip the day rather than send a weak briefing; note the skip in the weekly summary |

## Weekly checklist (Friday)

- Run the data quality check per site and compare with last week: `sudo scripts/data_quality_check.sh sunstar 14` (also panaya, oviva). It prints volume and approvals per topic, the keywords producing rejected rows, social rows missing sentiment or author role, posts stored as news (should be 0), duplicate and wire counts, approved source domains, translation coverage, enrichment failures, observer pool size, collector and feed errors, and the Japanese phantom-guard count. The baseline is `docs/DATA_QUALITY_REVIEW_POV_SITES_2026-10-05.md`.

- Alert volume per observer for the week, from `signal_alerts` by `instruction_id`. A domain watcher on a prospect site should land between 5 and 60 a week. Thousands means the instruction is a topic filter, not a watcher; zero for two weeks on anything but adverse media means the pool or the instruction is wrong.
- Read five alerts per observer. Note false positives and tighten the IGNORE list in the instruction. Changes are read live on the next run; do not restart.
- Spend from `llm_usage_log` for the week. Anything above USD 3 a day on a prospect site needs a reason.
- Briefings finalized this week against weekdays. Record skipped days and why.
- Replies and reactions from the customer. On wileytest Pascal reacted to the 1 October briefing; that is the signal a pilot is read.

## Things that bite

- Restarting a service runs every overdue observer immediately, so enabling an agent and restarting minutes before its slot sends two emails. Tune observers by SQL, not restarts.
- The sent ledger is `signal_alerts` itself. Deleting rows from it re-sends old alerts.
- Observer email goes out only when alerts clear the threshold. No email can mean an empty pool, not a broken sender.
- Social posts never carry a category, so the observer pool includes them only through the social branch gated at alignment 0.4 and no false-positive review. A social watcher on a site with no social evaluation model set sees nothing.
- On Bedrock-only sites the social evaluation model must be set per group or in .env; the template default `gemma3:4b` is not on the Bedrock list and evaluates nothing, silently.
- The briefing picks by relevance then recency with no alignment floor. Do not add one back; it drops the real picks.
- Incident and emerging-topic dates come from the article text or are labelled "reported on". A year that is not in any source is removed before finalize. If a customer questions a date, the review record on the briefing row shows what was checked.
- Observer report code has diverged between sites in the past. Checked today: Panaya, Sunstar and Oviva all carry the empty-report retry, the sent-ledger dedup and the invented-year strip, same as wileytest. Re-check with grep before trusting a site that was cloned or patched by hand.
