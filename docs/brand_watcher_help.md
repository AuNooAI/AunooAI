# Brand Watcher — How It Works

Brand Watcher is an adverse-media and brand-intelligence screen. It continuously collects news, social posts, official records, and employee reviews that mention your brands, classifies and scores everything, and raises alerts when something needs attention. This page documents every moving part.

---

## Core concepts

- **Brands** — each tracked entity (your brand + competitors) has a display name, brand keywords, a color, and per-brand configuration. One brand can be marked *primary*. Competitor brands are tracked deliberately: most views benchmark your brand against them.
- **Topics** — articles arrive through monitoring topics (e.g. `Brand Monitoring Wiley` for social, `Wiley - Brand Watch` for official records). The header brand selector scopes most tabs to one brand.
- **Relevance (topic alignment)** — every article and post is scored 0–1 for "is this actually about the brand?". **All brand views filter at relevance ≥ 0.4** to keep name-collisions (people called Wiley, unrelated companies) out of your numbers. Off-brand items still exist in the database; they are just excluded from brand analytics.
- **Sentiment** — articles and posts are classified (Positive / Neutral / Negative and variants like Concerned or Critical). The standard rollup is **net sentiment = (positive − negative) ÷ scored × 100**, shown as −100…+100. Unrated items never count in the base.
- **Categories** — news is classified into an 11-category taxonomy (Financial Performance, Legal & Regulatory, Customer & Product Issues, …) by a local model with LLM fallback; confidence and method are stored per classification.

## Tabs

| Tab | What it shows |
|---|---|
| **Dashboard** | The daily screen: problems & alerts, at-a-glance stats, news vs social sentiment (+ employee signal), sentiment over time, adverse-first news, most-amplified social, fans & critics. |
| **Brand Analysis** | The analyst view: a verdict header (composite risk score + the facts driving it), then themed sections — Reputation, Risk & compliance, Competitive position, Workforce, Coverage & sources. |
| **Comparison** | Side-by-side category and sentiment comparison across brands. |
| **Insights** | The LLM-written brand intelligence narrative (see *Insights generation* below), with regenerate and export controls. |
| **Articles** | The full classified article list: category filter chips, per-article sentiment, risk chips, factuality, case-status controls, CSV/JSON export. |
| **Social** | Social listening: brand swimlanes (per-brand sentiment timelines — click a lane to filter), scope toggle, two independently-filterable post lanes, diverging sentiment timeline, negativity themes, fans & critics with account typing. |
| **Accounts** | Per-account profiles built on demand: bio, followers, post sentiment, sample posts, tags, analyst notes, deep-dive and downloadable account report. |
| **Workforce** | Employee risk: Glassdoor aggregate ratings (overall, CEO approval, business outlook, recommend-to-friend, six sub-ratings), competitor rating comparison, recent employee reviews (pros/cons), and workforce risk findings. |
| **Incidents** | Case management: triage unacknowledged alerts (left), managed incident cases with severity/status/owner, timeline, and a tamper-evident evidence locker (right). |
| **Help** | This page. |

## Sentiment math & benchmarks

- Net sentiment appears as a signed number (e.g. **+57**, **−50**). The bar next to it splits positive / neutral / negative counts.
- Wherever your brand's net appears, a **competitor average** chip appears when at least one competitor has ≥ 3 scored items in the same window — so you can tell "we're down" from "the whole sector is down".
- The **Sentiment over time** chart buckets by ISO week (Mondays) and skips weeks with fewer than 3 scored items — those produce noise, not signal.
- A **perception gap** callout appears when social and news nets diverge by ≥ 25 points.

## Story-level flags

Articles covered by multiple sources form stories. Two flags are computed per story:

- **Negative consensus** — ≥ 3 scored articles and ≥ 70 % of them negative: the story's negativity is broad, not one outlet's take.
- **Polarized** — ≥ 4 scored articles with both poles at ≥ 30 %: coverage is split, expect contested framing.

Both appear on article detail panels and fire the `neg_consensus_story` alert rule.

## Alerting

Eight server-side rules run in the background (roughly every 15 minutes) over each enabled brand. Every event is deduplicated by rule + brand + time-bucket, so a persisting condition alerts once per cooldown window, not every cycle.

| Rule | Fires when |
|---|---|
| `neg_social_spike` | Negative social posts in the last 48h significantly exceed the prior 48h. |
| `high_reach_negative` | A single negative post exceeds the engagement threshold. |
| `news_net_negative` | News net sentiment falls below the threshold. |
| `category_spike` | A category's 7-day volume spikes vs its 30-day average. |
| `high_risk_finding` | A new high-severity risk finding is recorded. |
| `neg_consensus_story` | A story reaches negative-consensus (≥ 3 scored, ≥ 70 % negative). |
| `new_critic` | An author with no negative history posts ≥ 2 negatives (or one high-engagement negative) in 48h. |
| `coordinated_negative` | ≥ 3 distinct authors post near-identical negative content within 72h. |
| `glassdoor_deterioration` | Glassdoor overall rating drops ≥ 0.2 or business outlook drops ≥ 10 pts vs a snapshot up to 35 days back. |

Delivery channels: **in-app** notifications, **email** (configured recipients), and **webhook** (Slack-compatible JSON POST). Configure recipients, thresholds, and per-rule enable/disable in the **Alerts** modal (bell button on the dashboard). Unacknowledged events land in the Incidents tab triage column.

### Digest email

A daily or weekly **adverse-media digest** can be enabled in the Alerts modal (frequency + send hour, UTC). Per brand it covers: news sentiment net with competitor benchmark, employee signal (Glassdoor rating, outlook, review counts), new risk findings, alert events, and case actions. Idempotent per calendar period — restarts can't double-send.

## Risk taxonomy

Every negative or risk-adjacent article goes through a risk-detection pass (LLM with keyword fallback; a trigger regex pre-screens so the LLM only runs on plausible candidates). Seven risk types:

`legal_regulatory` · `financial_distress` · `fraud_integrity` · `esg` · `executive_misconduct` · `data_breach` · `workforce_labor`

Each finding carries severity (low/medium/high), confidence, and detection method, and can be case-managed (see below). Findings appear as chips on articles, in the Risk & compliance section of Brand Analysis, on the Workforce tab (workforce_labor), in the digest, and in exports.

## Case states & audit

Any finding or article can be marked **reviewed / escalated / dismissed** (the `act…` controls). Every state change is written to an append-only audit log with actor and timestamp. Dismissed findings drop out of adverse-first ordering. Case-action counts appear in the digest.

## Incidents & evidence locker

Promote anything worth managing into an **incident** (severity, status lifecycle open → investigating → contained → resolved/closed, owner, notes, full event timeline). Attach **evidence** (articles, posts, alert events, findings): the server snapshots content at attach time — sources get edited or deleted; the snapshot is the durable record. Each evidence item carries a SHA-256 content hash **chained to the previous item's hash**; *Verify chain* recomputes the whole chain and flags any tampering. Evidence is append-only by design — there are no edit or delete endpoints.

## Official & scholarly sources

Per-brand opt-in connectors (Sources modal, gear on the dashboard), polled every 24h per brand:

| Source | What it brings | Notes |
|---|---|---|
| SEC EDGAR | US company filings | Term-gated on title/summary. |
| CourtListener | US court opinions | Full-text APIs return judge-surname noise — the term gate drops records that never name the brand. |
| regulations.gov | US rulemaking dockets | Needs `REGULATIONS_GOV_API_KEY` (free). |
| Crossref / OpenAlex | Scholarly mentions | Citation noise handled by the same term gate. |
| Glassdoor | Employee reviews + employer aggregates | Needs `OPENWEBNINJA_API_KEY`. Reviews are company-scoped by Glassdoor company ID (no term gate); sentiment comes straight from the star rating (≥ 4 positive, ≤ 2 negative). If company matching picks the wrong employer, pin `glassdoor_company_id` in the brand config. |

Official records land as articles stamped with provenance (`official:<domain>`) and appropriate authority (SEC filing = very high factuality; a Glassdoor review = mixed — it's an anecdote, not a filing). Known name-collision entities can be excluded per brand (`official_keyword_excludes`).

## Workforce signal

With Glassdoor enabled, the platform tracks two layers:

1. **Aggregates** (refreshed daily, cached 24h): overall rating, review count, CEO approval, business outlook, recommend-to-friend, and six sub-ratings (work-life, culture, compensation, senior management, career, D&I). Shown on the Workforce tab with competitor comparison, on the dashboard Employee signal card, in the Analysis verdict, narrative, report, and digest. Every refresh also writes a **daily snapshot**, building a ratings-over-time series: the Workforce tab charts it and shows change-vs-last-month chips, and the `glassdoor_deterioration` alert rule fires when the rating or outlook slides — employer ratings move slowly, so a small drop inside a month is a real signal.
2. **Individual reviews** land as articles (title carries the star rating, summary carries Role/Pros/Cons) and flow into sentiment analytics. Reviews with strike/tribunal/layoff language feed the `workforce_labor` risk pass.

## Source quality (MBFC)

News sources are matched against a media-bias/factuality dataset at classification time. Factuality chips (high/mixed/low) appear on article rows and detail panels; authority weighting uses it so an SEC filing and an unknown blog don't count the same.

## Insights generation

The **Insights** tab narrative is generated on demand (Generate/Regenerate) from a structured data pack: category distribution, competitor mentions, risk assessment (score 0–100: recent negative share ×1.5 + worsening-trend penalty + alert weight), key positive/negative articles, social pulse, adverse risk findings, open incidents, and the employee/workforce signal. Required sections: Executive Summary, Category Analysis, Sentiment & Reputation, Social Pulse, Risk & Compliance, Workforce Signal, Forward-Looking Concerns. The prompt requires every claim to be grounded in the provided data — sections with no data say so in one line rather than speculating.

## Exports & reports

- **Articles CSV/JSON** (Export menu): Date, Title, Category, Sentiment, Source, Confidence, Method, URI, Relevance, Factuality, Bias, **Risks**, **Case Status**.
- **Social CSV** (Social tab → Export CSV…): full matching set (not the on-screen sample), ordered brand → sentiment → date; includes matched keywords, engagement counts, and — for authors with a built Account Profile — followers, verified, tags, analyst note, and profile summary columns.
- **HTML brand report** (Export menu → HTML report): a self-contained interactive file covering Overview, Analysis, **Risk & Compliance**, **Workforce Signal**, Insights, and Social (including static brand swimlanes) — safe to email, works offline.
- **Social / Account reports**: dedicated HTML reports from the Social and Accounts tabs.

## Scheduling & cadence

| Job | Cadence |
|---|---|
| Social + news collection | Per monitoring-group schedule. |
| Classification & risk pass | After each collection cycle. |
| Adverse alert rules | ~ every 15 min. |
| Official sources (incl. Glassdoor) | Every 24h per brand per source. |
| Glassdoor aggregates cache | 24h TTL (Refresh button on the Workforce tab forces it). |
| Digest email | Daily at the configured hour, or weekly on Mondays. |
| Language recovery (non-English rescore) | Hourly, bounded batch. |

## Configuration quick reference (per brand, `config` JSON)

| Key | Purpose |
|---|---|
| `extra_sources` | Enabled official sources (list of keys). |
| `official_keyword_excludes` | Drop official records containing these phrases (name-collision entities). |
| `social_keyword_excludes` | Suppress social keyword collisions. |
| `glassdoor_company_id` | Pin the exact Glassdoor employer when name search is ambiguous. |
| `topics` | Monitoring topics attached to the brand. |

Server environment keys: `OPENWEBNINJA_API_KEY` (Glassdoor), `REGULATIONS_GOV_API_KEY` (regulations.gov), `COURTLISTENER_API_TOKEN` (optional, higher rate limit).
