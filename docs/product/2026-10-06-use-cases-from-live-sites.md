# What customers use Aunoo for: use cases from four live sites

Compiled 6 October 2026 from the databases of four sites: Sunstar (`sunstar`), Wiley (`wileytest`, the production Wiley site), Oviva (`oviva`) and our own development site (`bugfixing`, DB `test`). Every example below is a real item the system produced, quoted or lightly shortened. Counts are rows in the site's database on 6 October.

## The four sites at a glance

| Site | Who it serves | Main question it answers | Articles held | Analyst agents |
|---|---|---|---|---|
| Sunstar | Japanese oral-care maker (GUM, Ora2, BUTLER) | Is the medical link between oral health and whole-body health being accepted, and what are Lion, Colgate, P&G, Haleon and Kao doing about it? | 34,921 | 4 |
| Wiley | Academic publisher | What in science funding, research integrity, AI and competitor moves will change our business? | 896,684 | 7 |
| Oviva | Digital weight-loss and diabetes provider (UK, Germany, Switzerland) | What are patients saying about us, and what are the GLP-1 clinics (Noom, Voy, Numan, WeightWatchers...) doing? | 3,503 | 3 |
| bugfixing | Our own market products and pilots | AI-SOC vendor market (feeds aisocnews.com), EV battery cells for a PowerCo pitch, Swiss election disinformation | 242,931 | 1 |

"Analyst agent" means a standing instruction in plain English ("flag competitor moves on oral-systemic health") that the system applies to every new article, raising alerts and writing reports.

## Business problems we solve, with examples

### 1. Catching reputation threats early

Customers want to hear about complaints, accusations and integrity problems before they spread. The system reads news and social posts, flags the adverse ones, rates severity, and groups them into named issues.

- **Oviva, patient complaints on social media.** The "Adverse Media Monitor" flagged a patient who said they were "ghosted": missed prescriber appointments, no reply by chat, email or phone, and delayed medication that interrupted treatment. It also caught a German healthcare provider reporting that 5 of 6 patients dropped out of the Oviva programme, and repeated posts calling Oviva "scammers and liars".
- **Wiley, research-integrity problems.** The system raised "Wiley investigating book chapter on biodiversity for fabricated references, including a non-existent rewilding study", and a Bluesky post sharing a Wiley paper with the instruction "use sci hub to bypass the paywall". Wiley also has an open incident in the incident workflow: a False Claims Act lawsuit over federal grant overcharging.
- **Oviva, sector risk.** The system logged "Concerns medical weight-loss treatments are being advertised to vulnerable eating disorder patients" as a medium ESG issue for the whole category.

### 2. Watching named competitors

Each site tracks a short list of rivals in news, social media, Glassdoor and company data. The system writes a dated summary per competitor and notes when coverage jumps.

- **Oviva.** Noom joined the Medicare GLP-1 Bridge programme with a $50 copay. WeightWatchers is pivoting to GLP-1 medication under a new CEO, Stephen Bye, from 10 September 2026. HelloBetter disclosed a data breach on 30 September, and the system noted coverage jumping to 19 articles in a day against a usual 0.7.
- **Sunstar.** P&G's Crest and Oral-B began offering a free professional-education course framed around oral-systemic health, which is Sunstar's own positioning. The system also logged Colgate's CEO stepping down and an analyst downgrade of Haleon.
- **Wiley.** Elsevier's domains were briefly hijacked to redirect to a LAPSUS$ page. Elsevier withdrew a five-year-old paper linking vaccines and SIDS. SAGE was found running library promotions in Thailand that carried a database termination warning. Pearson faced a $17.3 million internal fraud claim.

### 3. Monitoring a whole market, not just a few rivals

For a market, the system tracks dozens to hundreds of vendors and writes a cited monthly briefing: who launched, raised, partnered, hired or stumbled.

- **AI in the security operations centre (bugfixing, published as aisocnews.com).** 143 vendors tracked. In September the system flagged agentic SOC launches from Splunk, Exabeam, CrowdStrike and Cribl (Cribl claimed a 50% cost cut). The site is free to read. MCP access, which lets Claude, ChatGPT or a customer's own agents query the data directly, costs $139 a month.
- **EV battery cells (bugfixing, built for a PowerCo conversation).** The September briefing led with Gotion taking a 49% stake in PowerCo's Sagunto gigafactory for €1.1 billion, with three LFP joint ventures to follow.
- **Oral care (Sunstar)** and **digital weight loss (Oviva)** each get the same monthly briefing for their own category. Oviva's September briefing opened with Noom's distribution deal with Solera Health.

### 4. Tracking whether a scientific claim is winning the argument

Sunstar's strategy rests on one idea: gum health affects diabetes, heart disease and dementia. They need to know whether doctors and policy makers are adopting it, in each market, and whether anyone is overstating it in a way that could backfire.

- **Eight countries, seven languages.** Separate topics for Japan, the US, Germany, France, Italy, Spain and Brazil, plus a research topic. Each carries local search terms such as オーラルフレイル (oral frailty), Parodontitis Alzheimer and periodontite diabetes.
- **Adoption signals.** The "Professional and policy momentum" agent flagged that the American Society for Microbiology's new textbook treats oral-systemic health as a core theme. A Brazilian study of 279,000 people was picked up in the weekly country summary.
- **Overclaiming.** The "Evidence Watch: claims ahead of the science" agent has written 25 reports. Its latest flagged an FNN.jp article that said bleeding gums "trigger" diabetes and dementia, which is stronger than the evidence supports.

### 5. Reading the policy and funding climate

Wiley's revenue depends on research funding, open-access rules and AI licensing. Most of its topics track those forces rather than companies.

- **Topics:** US Federal R&D Pullback, University Grants & Science Infrastructure, Compensatory R&D Investment Abroad, Open Science Transition, Attacks on Expertise & Peer Review, Patent Cliffs.
- **AI and content licensing.** The licensing agent flagged a Third Circuit ruling that non-generative AI training infringed copyright, Anthropic's proposed opt-out model for Australian content (with the ABC pushing for paid licences instead), and Reddit restricting access to stop AI scraping.
- **Research integrity across the industry.** A biology journal pulling more than 100 papers for peer-review manipulation, and mathematicians warning that arXiv is being flooded with low-quality AI papers.

### 6. Geopolitical early warning

Wiley and bugfixing both run a geopolitical hotspot topic (191,252 articles on Wiley). An agent flags early signs of instability that could affect operations or markets.

- Recent high-severity flags: the US-Iran conflict and its unclear scope; NATO scrambling jets after a suspected Russian drone incursion; Latvia's election under Russian hybrid-warfare pressure.

### 7. Election disinformation monitoring (internal project, bugfixing only)

We built this for the Swiss federal elections in 2027. It watches news, social media and Telegram in English, German, French and Italian.

- **Targets:** the 29 November 2026 federal votes, the EU treaty package (Bilaterals III), the Federal Chancellery, the intelligence service, and each federal councillor.
- **Output:** 207 distinct claims extracted and tagged by likely origin. Examples: "Russia is conducting hybrid warfare against Switzerland including disinformation campaigns" (French-language sources) and "SVP initiatives are primarily propaganda vehicles for Christoph Blocher" (domestic, German).

### 8. Horizon scanning for emerging technology

Several topics look further out, with forecast assessments that test articles against stated scenarios.

- **Wiley:** early signs of AGI (157 reports), quantum computing (the $300 million US investment in D-Wave, Rigetti and Quantinuum), and patent cliffs in pharma.
- **Sunstar:** regenerative dentistry, such as enamel regeneration and dental stem cells. The system noticed coverage jump from under one article a day to seven on 19 September after new enamel-remineralisation studies.

### 9. Hearing customers and the public

- **Sunstar** collects 9,196 consumer posts from Reddit communities such as r/askdentists, about topics like hydroxyapatite toothpaste and mouth taping. It has run simulated focus groups on five topics.
- **Oviva** reads patient voices per brand, and its team queries them from Claude: `get_brand_voices` and `get_social_posts` were called 45 times.
- **Wiley** runs a "Negative Social Sentinel" over academic Bluesky and X (40 reports).

### 10. Benchmarking vendors against each other (Market Horizon)

Customers want to know where each vendor stands: who is big, who is growing fastest, who just raised money, and who has dropped out. Market Horizon places every vendor on two scores out of 100, computed over the last 90 days:

- **Scale:** headcount, followers, funding and customers.
- **Momentum:** hiring, launches and mentions.

Vendors then fall into size tiers (Emerging, Established, Scaling, Executing) and growth bands (Holding, Growing, Accelerating).

The scores come from public data we collect ourselves. On bugfixing that is 1,649 snapshots of vendor web pages, about 2,100 job postings (LinkedIn and company careers pages), 507 LinkedIn company profiles and 426 funding records. Each Horizon page states what it does not cover: "It does not rate product quality, customer satisfaction or strategy."

- **AI in the SOC (bugfixing, 90 vendors placed).** 7AI leads on scale (97) after its $130M Series A. Exaforce (92) and Anvilogic (90, with Snowflake investing) come next. Nebulock has the highest momentum (80) on a $25M raise, while still mid-sized. The page also handles vendors it cannot compare fairly:
    - **Large incumbents are listed but not scored:** CrowdStrike, Palo Alto Networks, Microsoft, Splunk/Cisco and Torq, among others. A note explains why: "Its headcount and followers are the whole company's."
    - **Exits are recorded with the source:** Kenzo Security (bought by Rapid7), Radiant Security (its AI SOC technology bought by Cribl, 19 August 2026), Redblock (closed).
    - **Pivots are recorded:** Zaun is noted as "now security for AI ... no longer AI for security operations."
- **Digital weight loss (Oviva, 6 vendors placed).** Noom ranks first (scale 85, momentum 75) and Oviva second (scale 81, momentum 59, after its €200M Series D). Voy is small but has the highest momentum (76). Juniper, Numan and Second Nature are in the Holding band.
- **EV battery cells (13 vendors)** and **enterprise test automation (10 vendors, for Panaya)** use the same method. In test automation, Nova Intelligence is the smallest vendor but is hiring, after a $40M raise.

### 11. Trend forecasting

Three tools look ahead. Each works from the articles a topic has already collected.

- **Scenario tracking (Forecast Assessment).** For each topic the system writes scenarios at three time horizons, then sorts new articles as supporting or contradicting each scenario. Each scenario gets a verdict: Accelerating, On-track, Stalled or Off-track. Wiley's run on 3 August is the best example:
    - "Federal R&D Funding Decline and Policy Uncertainty": **Accelerating**, with 128 articles supporting and 18 contradicting.
    - "Strategic Partnerships Accelerate Quantum Progress": **Accelerating**, 39 for and 0 against.
    - "Enterprise [quantum] Adoption Faces Persistent Barriers": **Off-track**, 4 for and 27 against. In other words, the news says the barriers are falling.
    - "Diamond Open Access & Subscription Model Erosion": **On-track**, 5 for and 0 against.
    - Treat these 3 August verdicts as illustrations, not findings. The model that judged them (Kimi) turned out to be unstable when we tested it on 6 October: it gave a different answer on a quarter to a third of articles when asked again. The verdicts were also counted with syndicated copies included. See "Scenario tracking fix, 6 October" at the end.
- **Emerging topics.** The system clusters new articles and reports stories that are new and growing.
    - Sunstar's recent ones are on point: "Oral microbiome health as wellness trend", syndicated stories pushing oral microbiome products into the mainstream, and the gum disease and Alzheimer's bacteria studies of 18–20 September.
    - On Wiley it picked up "AI CEOs call for development slowdown" and "OpenAI AGI arrival claims", which feed the AGI watch.
- **Future Horizons and impact timelines.** These are one-off AI reports per topic that lay out likely, plausible and possible futures, with citations. There have been 41 runs on Wiley, 33 on Sunstar, 6 on bugfixing and 3 on Oviva.

## How customers receive it

- **Alerts and agent reports.** Wiley saved 1,094 agent reports and has 56,235 alerts. The busiest agents are Scientific Publishing Watcher (221 reports) and Emerging Geopolitical Signals (208).
- **Daily briefings.** Wiley gets one most weekdays (150 to date). Sunstar has 7 and Oviva 1.
- **Monthly market briefings** with citations, for each market (see section 3).
- **"What changed" summaries** per topic and per brand, written when coverage moves. These supplied the HelloBetter, WeightWatchers and Brazil examples above.
- **Inside Claude, through MCP.** Oviva made 270 tool calls between 4 September and 1 October, mostly article search, social posts, brand stats and voices. On the other sites MCP use is still light (6 calls on Sunstar, 6 on Wiley).

## Gaps the review turned up

- **Sunstar:** Kao is switched off in English and Japanese, and the UK press topic is off (UK comes in via RSS instead), so those markets have thin coverage.
- **bugfixing:** the copied Wiley-style topics (R&D pullback, patent cliffs and others) stopped collecting on 19–20 August. They are leftovers and not a live use case.
- **Scenario tracking produced no evidence from early September until 6 October.** Fixed and re-tested; see "Scenario tracking fix, 6 October" below.
- **Oviva's emerging topics are off-subject.** Its top items are Nigerian healthcare investment, Pacific climate finance and an open-source code editor. The detector does not seem to be limited to Oviva's topics.
- **Sunstar has no Market Horizon.** It has an Oral Care market and some vendor data (122 job postings), but no ratings have been computed. Wiley has no market set up at all.
- **Uneven use of features.** Scenario tracking runs on Wiley and Sunstar but not on Oviva. Focus groups exist only on Sunstar. The incident workflow has one live incident, on Wiley.

## Scenario tracking fix, 6 October

From early September every scenario on Wiley, Sunstar and bugfixing came out "Inconclusive", with no articles for or against.

### What was wrong

- **Checks ran too early.** On 21 September the forecasts were rebuilt and checked the instant they were created, so there were no newer articles to read. Automatic re-checking was switched off, so nothing checked them again.
- **The matching step refused large topics.** The model that matches articles to scenarios now runs on the CPU, and it refuses any job over 1,500 article-scenario pairs. A full topic needed about 10,000.
- **The judging model was unstable.** Kimi gave the same answer on only 66–77% of articles when asked three times.
- **Duplicates counted as evidence.** Syndicated copies counted as separate evidence: 8 of 37 matched articles on Sunstar's main topic were copies.
- **A stale scenario file hid the current one.** On Wiley, Open Science had an old May "overlay" (the file that merges a forecast's 13 raw scenarios into the 5 shown in the deck) beside the current one. The system loaded the old one, which matched none of the current scenarios, so every check fell back to 13 overlapping scenarios. With that many overlapping scenarios most articles fit several equally well and go unmatched, and the article sample shrinks. Two other Wiley topics had the same leftover file but happened to load the right one.

### What changed

- **Jev now judges each article, with a clearer question:** "more likely, less likely, or no bearing". In the same test Jev gave the same answer on 93% of articles and agreed best with the strongest independent judge, Claude Sonnet 5. It costs under a cent per check.
- **Matching works on large topics.** The article pool is cut to fit the matching limit, using an even spread across the period.
- **Copies merge into one story.**
- **A verdict needs evidence and time:** at least 5 stories that move a scenario either way, and at least 4 weeks since the forecast.
- **Automatic re-checking is back on** for Wiley and Sunstar. It runs monthly per forecast; the first pass is due about 5 November.
- **The right scenario file is always used.** The three stale overlay files on Wiley were retired. The system now picks whichever overlay matches the forecast and logs a warning when more than one exists.

### Where the forecasts stand

- **All 11 Wiley and Sunstar topics were re-checked, and every scenario is Inconclusive.** That is the honest answer 15 days after the forecasts.
- **Three Wiley topics already have enough evidence** and should get verdicts at the November pass: Quantum Advantage (25 stories for, 2 against), Patent Cliffs (23 for, 10 against), and Open Science's "Reputation Economy Emerges" (5 for, 1 against). Open Science was re-checked on its 5 proper scenarios after the overlay fix: 44 stories matched, against 17 on the 13 raw scenarios.
- **Most Sunstar country topics collect too few articles to judge.** Japan had 3 since the forecast, and France had 1.

### Tested since the fix

- **The scheduler starts checks by itself and reaches real verdicts.** On bugfixing it re-checked the AI-SOC forecast on its own at 18:11 on 6 October, 30 days after the forecast. It used Jev and cut the pool to 300 articles. One scenario got a verdict: "Multi-Agent Systems Enable Parallel Security Operations" is **On-track**, with 4 stories for and 1 against. The other four stayed Inconclusive.
- **A check started through the app's own API runs end to end.** It ran as a background job in the live service, used Jev for both halves and finished in 12 minutes. That forecast (bugfixing's copy of "U.S. Federal R&D Pullback") had no merged scenarios, so it matched only 4 of 115 articles. Following that up uncovered the stale-overlay problem above.
- **The fixed pages work over the web with a real login:** the article view, latest articles and the source-flow chart all return normally.
- **Not established:** whether Jev's answers are right. We measured only that it is consistent and agrees with another strong model.
