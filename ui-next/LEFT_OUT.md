# Left out of the redesign, to do later

These are features of the old pages that the new pages (`/gather/next`, `/operations/next`,
`/anticipate/<tab>`) do not have yet. None of them is blocked. Finish them before the old pages are
retired.

PAM (Power, Attention & Money) was removed on 14 Oct 2026 because the feature is dead: its code is
gone from both the old and new pages (commit 634f7f19). Bugfixing's `pam_*` tables were dropped on
15 Oct 2026 by migration rt_002_drop_pam_tables, after a backup to
backups/pam_tables_test_20261015.sql.gz. Wiley and wileytest still run the PAM code and keep theirs.

## Still to do

Every Explore tab is rebuilt, and the features left out along the way were added on 15 Oct 2026
(below). What's left:

- Not checked in a browser: the 3D globe on GeoHotSpots (the test browser has no WebGL; where a
  browser lacks it, the globe isn't offered and a failure falls back to the street map), and the
  Brand Watcher social swimlane, which needs two or more brands with "Brand Monitoring <brand>"
  social posts (bugfixing files its social posts under market topics, so it stays hidden there).
- Never run for real: share by email, podcast audio, AI screening, arena runs, imports and most AI
  report writers (the four real checks on 15 Oct covered Anticipate, the Briefing Desk, an Observer
  Agent run and a Gather keyword group).

Bugfixing serves the new pages in place of the old ones since 15 Oct 2026 (AUNOO_UI_NEXT=1, see
app/middleware/ui_next_redirect.py). The old pages still exist; rolling the new pages out to other
sites has not been requested.

## Backend fixes on 15 Oct 2026 (bugfixing, wiley, wileytest)

- Request-time table creation moved into migration rt_001_runtime_tables (one copy per site, on
  each site's own head; applied on all three): tracked_emerging_topics and the
  keyword_monitor_status default row. The read routes no longer create anything.
- Market Monitor shared investors (bugfixing only; wiley and wileytest have no Market Monitor): the
  Analysis panel now uses the full list's calculation and shows "the 25 backing the most vendors,
  of 31"; it used to stop at LIMIT 25 and read as a count.

- Manual Observer Agent runs (Run, Run all) now record the agent's last run, status and run count,
  as scheduled runs did; the next scheduled time is untouched. Commits c57630d2 / d71478c1.
- GeoHotSpots "no hotspots" was not a bug: the module is off on bugfixing and its last run read
  articles from 7 Sep 2026, so the default 30 days is empty (189 hotspots in 90 days, 769 in a
  year). The page now says so when a period is empty and offers a longer one.

- Media sources are keyed by their name (`source` is the `mediabias` primary key; there is no id
  column), so searching, editing and deleting sources failed on every site. The id the API returns
  is now the source name, the routes take it as a path string, and the facade looks sources up by
  `source`. Commits 23c324ac (fix/ingest-pipeline-spec) and 8081aae9 (this branch).
- Date filters in the exploratory search dropped every result, because `app/kissql/executor.py`
  compared `publication_date` as a number. It now compares as numbers when both sides are numbers,
  else as dates, and understands today, yesterday, last_week, last_month, last_year and spans like
  7d. Exploratory Analysis now sends date filters to the server as ISO dates, so Patterns and the
  map follow them; only keyword search, whose route takes no filters, still filters in the browser.

## Settings rebuilt on 15 Oct 2026

- All seven Settings pages at `/settings/<page>`: App Configuration (`config`), Topic Editor
  (`topic-editor`), Prompt Engineering (`prompts`), Model Bias Arena (`bias-arena`), Exploratory
  Analysis (`exploratory`), Database Editor (`database`) and Analytics (`analytics`). The old
  addresses redirect there when AUNOO_UI_NEXT is on. No new backend routes were needed.
- Old bugs fixed on the way: deleting a topic always failed (422); saving a topic dropped its other
  settings; renaming a topic made a duplicate; prompt saves reported success after a refusal; the
  topic import opened in "Replace" mode, which deletes every topic config without asking (now
  "Merge", Replace asks); multi-picked media-bias filters returned nothing; password rules weren't
  checked; bulk delete missed articles whose address has % or +; private notes vanished after
  saving; "Color by" did nothing on the analytics flow chart and its moving average sank to zero;
  the arena preview didn't encode the topic. Native alert/confirm/prompt boxes are gone.
- Left out: Reindex ChromaDB (always failed; ChromaDB was removed), the exploratory 3D view, the
  "Did you know?" filler, debug buttons, and controls the server ignored.

## Added on 15 Oct 2026: the features left out along the way

- Shared: share by email (`shared/ShareDialog.tsx`, all /api/share/* kinds and the Briefing Desk
  share), PDF, CSV and image exports (`shared/exports.ts`, jsPDF and html2canvas), a swimlane chart
  (`shared/Swimlane.tsx`) and a street map with clustering (`shared/StreetMap.tsx`, Leaflet and
  OpenStreetMap tiles). Leaflet, the globe, jsPDF and html2canvas load only when used.
- News Feed: share by email on the briefing, stories, incidents, narratives and article details;
  Markdown, PDF and CSV downloads; the briefing podcast (script and audio as separate steps, each
  asks first); arranging and hiding categories; the Five Signals block in article details.
- Brand Watcher: PDF, Markdown, print and PNG exports; Social settings (Gather's group settings
  dialog); the brand swimlane; the competitor-average social line; the PDF case report; one shared
  "add to incident" dialog. Fixed: "add or refresh monitoring" started paid collection without
  asking.
- Market Monitor: the coverage timeline (swimlane), thumbnails, account photos, clickable bars,
  the two-scale "who shouts loudest" scatter, and the street map under the vendor geography.
- Emerging Topics, Observer Agents, Briefing Desk, Saved: share by email, PDF exports (themes,
  saved incidents including the styled report, saved reports), and podcast audio for agent runs
  and reports (paid voicing, asks first).
- Module tabs: street maps with clustering on GeoHotSpots and Threat Intelligence, the 3D globe on
  GeoHotSpots, 14 chart image downloads, the threat briefing PDF, the threat actor cards, and
  coloured section cards on all four Insights reports. Fixed: the old globe put place names into
  its labels unescaped.
- Tested on the read-only server: share by email (send faked), PDF downloads (incidents 969 kB,
  narratives 15 kB), the Brand Watcher PNG and Markdown, the Market Monitor street map (12 tiles,
  17 markers) and, with sample points, the GeoHotSpots and Threat Intelligence street maps.
  Found and fixed in testing: a browser without WebGL blanked the page when the globe was picked.

## Done on 15 Oct 2026

- Explore phase 6: the four analysis-module tabs, GeoHotSpots, US Crisis Tracker, ScienceWatch and
  Threat Intelligence, each with all its sub-tabs, update/import and schedule dialogs, and the
  shared article details sheet. They show only where the module is switched on (all four are off
  on bugfixing). Changes from the old pages:
  - US Crisis Tracker and ScienceWatch: the header's Refresh wrote a new AI report while the
    report sub-tab was open. Refresh now only reloads; writing a report asks first.
  - AI runs now use the model picked in the filter bar; the old pages always used the server
    default. Update, classify and "run a schedule now" say how many AI calls they make first.
  - GeoHotSpots articles: paging and sorting did nothing (every page was the first 20), and a
    click only logged to the console. Several figures ignored the period. A run over a backlog
    of more than 500 failed; it's capped at 500.
  - US Crisis Tracker and ScienceWatch: "All time" failed or showed only a year or 90 days in
    places; breakdowns never reloaded on a period change; an empty search showed everything;
    a "full reclassify" button did the same as the normal one and is gone.
  - Threat Intelligence: type links ignored the type, the category trend chart never drew, a
    campaign filter read "undefined", and filter changes could land on an empty page.
  - Fake "trend" arrows on GeoHotSpots analysis (they were the average intensity) are gone.
  - Deletes ask first; failed saves, runs and deletes say so.

- Explore phase 5: Briefing Desk at `/explore/next/briefing-desk` (briefing list, open briefing
  with content and summary, reviewer findings and "finalize anyway", compose today's briefing,
  create, exports) and Saved at `/explore/next/saved` (starred articles, saved incidents, saved
  narratives, tracked emerging topics, podcasts with a transcript, saved reports). "Add to a
  briefing", left out of phases 1 and 4, is now in the article details sheet, News Feed incidents
  and briefing stories, and Emerging Topics cards. Changes from the old pages:
  - Writing a briefing again with the AI asks first; it replaces hand edits, which aren't kept.
  - "Create and add" added articles and incidents but not emerging topics; it adds all three now,
    and a theme reaches the briefing with its source articles (the old page sent none).
  - Removing a saved incident did nothing with "all topics" picked; it uses the incident's own
    topic now. Notes are attached by the saved row's id, not by name.
  - Starred articles that fail to load are listed as such instead of vanishing.
  - Removing a saved incident or narrative, deleting a podcast or a briefing asks first; failed
    loads and removals say so.
  - Left out: share by email, and the PDF and styled Markdown exports of saved incidents.

- Explore phase 4: Emerging Topics at `/explore/next/emerging-topics` (overview charts, cards,
  table and signal dashboard, card analysis, retire/restore/track/delete, retired list,
  high-novelty articles, Future Horizons, settings and schedule dialogs, Markdown and CSV export)
  and Observer Agents at `/explore/next/observer-agents` (agents, run dialog, add/edit dialog,
  schedules strip and table, and the saved reports the agents write, ten at a time). Changes:
  - Scan, Run now and running agents ask first and name the model and the amount read.
  - Three Emerging Topics charts drew data that doesn't exist (a random hit-and-miss pattern,
    every day in a window marked as a find, dots spread over invented dates). They now draw only
    the stored counts and dates.
  - Signal cards no longer all read "Society and other": the category came from the scanned
    topic, which a scan across all topics doesn't have, so the label is hidden then.
  - The signal dashboard now follows the urgency and velocity filters.
  - Unticking "Tag matching articles" on an agent is now saved; scheduled runs ignored it before.
  - "Dismiss all" inside one agent cleared every agent's matches; now only that agent's.
  - Deleting an agent, a theme or all themes asks first. Failed saves, failed runs (which reported
    "0 topics found") and failed deletes now say so.
  - The schedule strip covers the next 24 hours from now instead of wrapping tomorrow onto today.

- Explore phase 3: Market Monitor at `/explore/next/market-monitor`, all seven views (Findings,
  Analysis, Top voices, Market Maturity Map, Collection with its six sub-views, Reports, Vendors),
  the vendor page, the vendor lists and record lists behind each figure, the settings sheet (search
  terms, sources and schedules, health, scope) and the exports. Changes from the old page:
  - "Last 365 days" works. The pulse route accepts at most 90 days, so the old page's whole reload
    failed at 365; the pulse now asks for at most 90 and says which window it covers.
  - Costly actions ask first and say what they cost: bulk collection switches (after a dry run),
    Fetch now on a vendor page, bulk account profiling, rewriting a report, post review, timeline
    build, corpus rescan and keyword-group setup. None of them runs on load; nothing did before either.
  - Rewriting a report warned nobody that the server keeps no copy of the old text. It now asks.
  - A piece whose citation check failed could never be approved; the server's override is now offered.
  - "Notable and above" in Findings left out the material findings; it now includes them.
  - Rescanning the corpus or reviewing posts reloaded the list with a 100-row cap and no filters; it
    now keeps the filters. Source intervals no longer save silently on blur.
  - Vendor status controls offered only active, acquired and closed; pivoted and incumbent vendors
    showed as active. The list now comes from the server.
  - Failed review-task actions and failed analyses say so instead of disappearing.

## Done on 14 Oct 2026

- Explore phase 2: Brand Watcher at `/explore/next/brand-watcher`, all twelve sub-tabs (Dashboard,
  Brand analysis, Perception, Voices, Comparison, Insights, Articles, Social, Accounts, Workforce,
  Incidents, Help), the brand settings, classify, sources and Five Signals dialogs, the exports,
  and first-run setup. Changes from the old page:
  - Nothing paid or AI runs on load any more. The old page built xpoz account profiles for the top
    fans and critics (Dashboard, Social), wrote AI digests per Voices column, translated a case's
    coverage when it opened, and wrote the brand report when a brand had none. Each is now a button.
  - The JSON article export now downloads; the old one fetched the data and dropped it.
  - Brand saves that fail say so; the old page logged them to the console only.
  - Brand analysis counts only this brand's open incidents, and compares competitors over the whole
    period instead of the Articles tab's current page.
  - The Workforce read still refreshes a Glassdoor cache older than a day, as before.
- Explore phase 1 at `/explore/next`: the frame (shared filters, tabs in the URL, module switches,
  the dedicated Brand Watcher tab set), Overview, News Feed, Timeline and Swiss Election Watch with
  all ten sub-tabs. Old links (`/explore?tab=swiss_disinfo`, `#emerging-topics`) map onto the new
  tabs. Changes from the old page:
  - Incidents and narratives now reload their stored results when the topic or dates change; the
    old page read them once per visit. Their dates follow the filter bar's date range (the old
    page kept a separate one you couldn't change).
  - Hiding an incident no longer starts a full incident run with the AI.
  - Saving an incident works with several topics picked (it used the incident's own topic); the
    old page did nothing unless exactly one topic was picked.
  - Incident settings now take effect. The old modal's saves always failed the server's check
    (snake_case sent to a camelCase model), and the runs read the prompts from a browser key the
    modal never wrote. The new dialog checks the prompts on the server and keeps them in that key.
  - A persona change asks for that persona's briefing once; the old page made a second, forced
    call that likely used the previous persona.
- Submit Articles rebuilt at `/submit-articles/next`, linked from the new Gather page. It analyses
  links (streamed) or pasted text, lets you correct the result, saves it, and can draft incidents.
  Links that fail are listed apart and are never saved. The old page sent `modelName`,
  `summaryLength` and `summaryVoice` to a stream that reads `model_name`, `summary_length` and
  `summary_voice`, so its link analyses ignored those choices; the new page sends what the stream
  reads.
- Auspex chat: the floating button on every new page opens it in a side panel. Chat and deep
  research stream from the real routes; charts draw with the library's charts; conversations,
  summary and export work. Deep research now saves its question and report into the chat.
- Bundle brief editor: "Edit and curate" on each bundle card in Deliverables. Exec summary, themes,
  decision framework, what's changed, per topic, events and approval, with locks and regenerate.
- Topic setup wizard: "Set up topic", the sidebar item and `?onboarding=true` open the design's
  wizard on the real `/api/onboarding` routes, on every new page. AI counts as configured when the
  site has models (Bedrock sites have no AI key in `.env`).

- Situation Assessment shows threats and opportunities as two columns, and recommended actions as
  three timeframe columns. Sections that don't parse stay Markdown (c5f0e5a3).
- PNG export on the five analysis tabs and the five generators (ebbf5781).
- Save stores all five analysis tabs, and a saved analysis stays open across tabs (c076d663).
- Organisational profiles can be created, edited and deleted from Configure. The profile list now
  returns `monitored_brands`, so editing no longer clears them (691016d0).
- The newsletter editor has a toolbar, shortcuts, undo, preview and article insert (17a14a6e).

## Not tested for real

Every action that calls an LLM or writes data: the five generators, forecast assessments, saves
(analyses and profiles), podcast, topic promote and scan, bundles and reports. The test harness
blocks these to avoid cost. The profile save was checked by intercepting the request in the
browser, so its payload is right, but it has not been sent to the server.
