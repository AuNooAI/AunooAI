# Brand Risk v2 — event-driven risk assessment, statistics for detection only

_2026-08-14 · Spec only, nothing built. Replaces the same-day statistical draft after
review: statistics on a small corpus can detect that something unusual is happening, but
it cannot assess whether it matters. Detection and assessment are separated accordingly.
Revised same day after external review (verified against the live trees): corrected
"what exists" claims, `bw_daily_stats` found unusable as a baseline, and implementation
decisions added for issue identity, historical semantics, peer eligibility, and
calibration. Covers the Brand Watcher risk score shown on the dashboard, in PDF exports,
and in generated narratives._

**Branch caveat for reviewers:** every "already exists" claim below refers to the
canonical tree at `/home/orochford/tenants/bugfixing.aunoo.ai`, branch
`emergencyfix/embedding-health-latency-load`, which is 128 commits ahead of origin/main
and unpushed. A fresh clone of the remote will not contain the escalation-tiers work
(`4f7903fa`) or anything after it.

## The problem

Today's risk score is a weighted sum of coverage percentages and volume spikes:

```
score = negative share of coverage (%)   × 1.5
      + worsening vs prior 4 weeks (pp)  × 2      (only if worsening)
      + 5  per category coverage spike (≥2× normal weekly volume)
      + 10 extra per severe spike (≥3× normal)
bands: <30 Low, 30–59 Elevated, ≥60 High
```

The 2026-08-14 Wiley report scored 39/100 "Elevated" with 30 of the points coming from
coverage spikes the report itself called neutral (Wiley acting as a publisher), and the
sentiment contribution resting on 2 negative articles out of 82. Meanwhile a single
article about a peer-review bribery investigation — the one genuinely risk-relevant item —
contributed about 1.8 points.

That inversion is the core defect, and it is not fixable with better statistics, because
the formula answers the wrong question. Frequency arithmetic on ~11 articles a week
measures media metabolism. Risk management rates *events* by severity and impact in
context: one regulatory investigation outranks eighty neutral mentions regardless of any
distribution, and forty mild complaints never sum to one fraud case. A risk register
takes the maximum of active risks; it does not add up article counts.

Implementation faults that ride along and get fixed in passing: sentiment math counts
category rows so multi-category articles vote more than once; spike windows use `NOW()`
instead of the report window; and the formula exists in three hand-synced copies
(`brand_watcher_routes.py`, `BrandWatcherTab.tsx`, `exportService.ts`).

## Principles

1. **Statistics detect; they never assess.** Volume anomalies against the brand's own
   history are a legitimate small-sample question ("is this abnormal for this brand") and
   produce an *Attention* signal. That layer never emits the word "risk".
2. **Risk is a property of the event, assessed at the event level.** At 2–15 flagged
   articles a week, the honest method is to read them: classify what happened, once per
   underlying event, not per article.
3. **The brand's risk level is the maximum severity of its active issues,** modified by
   breadth and momentum — never a sum of counts.
4. **Clinical classification is the platform's; escalation language is the customer's.**
   The platform does assign each issue a low/medium/high severity — that is a clinical
   classification, stated as a fact with its justification, like a sentiment label. What
   it never does is escalate: words like "Elevated", "crisis", or any alarm framing come
   only from thresholds the customer defined in advance (the escalation-tiers principle —
   Pascal Hetzscholdt, 12 Aug; commit `4f7903fa`). A platform-invented "39/100 Elevated"
   is an escalation judgment in numeric costume, and it goes away.
5. **Peer coverage is context, not arithmetic.** "Peers are covered by the same story"
   is an annotation on an issue that changes how it reads, not a multiplier on a score.

## What already exists (verified in code and data, 2026-08-14; wbm unless noted)

- **`bw_article_risks`** — the adverse-screening pipeline's typed findings: `risk_type`,
  `severity` (low/medium/high), `confidence`, LLM-assessed. The code taxonomy
  (`RISK_TYPES`, `brand_watcher_routes.py:4703`) already has **seven** types:
  legal_regulatory, financial_distress, fraud_integrity, esg, executive_misconduct,
  data_breach, workforce_labor — wbm's stored rows show only five because two have never
  fired. Screening runs inside the tracker path in `brand_watcher_routes.py` (INSERT at
  ~4785), **not** in `brand_watcher_monitor.py`. Coverage is the gap: 50 rows total
  since early July, Wiley itself has just 2 (Jul 5–26).
- **`bw_article_stories`** — story grouping: 1,799 groups over 2,164 rows, but almost all
  singletons (largest group 16). Grouping exists; cross-article merging barely happens.
- **Escalation tiers** (`app/services/escalation_tiers.py`, spec
  `docs/CUSTOMER_ESCALATION_TIERS_SPEC.md`) — customer-defined labels + thresholds,
  deterministic evaluator, rule vocabulary already including `requires_high_risk` (a
  high-severity `bw_article_risks` row in the window). Unconfigured brands stay clinical.
- **`bw_daily_stats` is NOT usable as a history baseline.** The updater
  (`brand_watcher_routes.py:2509–2517`) writes the brand's *all-time cumulative* category
  count into the current day's row on every tracker run — confirmed in data: wbm Wiley
  "daily" values run 252→285 over the last week, monotonic snapshots, while true daily
  scored volume is 0–5. Attention must query `articles` directly. (First-differencing
  consecutive snapshots can approximately recover a daily series for backfill; that is an
  optional repair, not a dependency.)
- **Sentiment-scored history: ~17 weeks** (back to 2026-04-14 on wbm Wiley), which is
  also the effective ceiling on any volume baseline until the daily-stats repair.
- **`bw_incidents`** (9 since Jul 13) plus known external events (peer-review bribery
  investigation, $44M AI-licensing backlash) — thin but real calibration ground truth.
- Weekly volumes are small (Wiley ~11 scored articles/week; peers 1–11/week). Peer sets
  with usable volume exist on wbm and wileytest only; wiley prod has zero brands.

## Design

### Layer 1 — Detection (Attention)

Pure statistics against the brand's own history, producing an **Attention** readout:
current coverage as a multiple of the brand's normal weekly volume, per category and
overall, with persistence (sustained days) and spread (distinct sources). Computed by
querying `articles` joined through `bw_article_categories` directly — window-relative
date math on `publication_date`, `COUNT(DISTINCT article_uri)` — over all available
history, minimum 8 weeks (`bw_daily_stats` is excluded until repaired; see above).
Displayed as "coverage running 5× normal in Product & Innovation (19 articles vs
3.8/week average)" — a visibility fact, no band words, no risk vocabulary. High
attention is also a *trigger*: it queues the spiking coverage for Layer 2 screening even
when nothing is sentiment-negative, because hostile events can arrive in neutral-toned
wire copy.

### Layer 2 — Issue assessment (Risk)

**Screening coverage first.** Extend adverse screening so every article that is negative,
in a risk-relevant category, or part of an attention spike gets screened. Screening
records go to a **new `bw_screening_verdicts` table** (`article_uri`, `brand_id`,
`screened_at`, `model`, `prompt_version`, `outcome` = risk_found | no_risk_found), so
coverage is distinguishable from silence without polluting `bw_article_risks`, which
keeps its current meaning: typed findings only. The screening logic is extracted from
`brand_watcher_routes.py` into `app/services/brand_screening.py` during this rework
(it is being rewritten anyway). Taxonomy gains **one** new type, product_safety, for
eight total. Cheap model per the cost rules (kimi/nova class); at these volumes the
spend is cents per brand-week.

**Issues, not articles.** Risk-flagged articles are grouped into *issues*: one underlying
event, assessed once. An issue carries:

- event type — one primary type from the eight; if a confirmed-same event spans types
  (a breach that becomes a lawsuit), the primary is the highest-severity finding's type
  and the others are kept as secondary,
- severity low/medium/high — the max of its articles' screening verdicts, with the
  LLM's one-sentence justification kept for display,
- first-seen / last-seen, article count, distinct sources (breadth),
- momentum: spreading (new sources this week), persisting, or fading. Auto-resolve is
  severity-scaled (decided 2026-08-14): an issue with no new coverage resolves after
  28 days if high severity, 14 if medium, 7 if low. Returning coverage reopens the same
  issue with its history, never a new one,
- peer-context flag: same story matched in peer brands' coverage → annotated
  "sector-wide", displayed with the issue, no score effect. Customer-facing only where
  the tenant has ≥2 eligible peers (definition below; wbm and wileytest today); on
  thinner tenants the flag is computed and stored but omitted from reports, silently
  (decided 2026-08-14).

**Brand risk level = max severity across active issues**, with modifiers stated as
facts, not folded into arithmetic: "1 high-severity active issue (legal/regulatory:
peer-review bribery investigation, 12 articles, 5 sources, first seen Jul 28,
spreading), 2 medium issues." The Wiley case under this design: the bribery
investigation is the risk story at whatever severity screening assigns it; the
Product & Innovation spike is attention, not risk — which matches what the report's own
prose concluded despite its 39/100.

### Layer 3 — Customer context (escalation tiers)

The severity *language* routes through the existing escalation-tier evaluator:

- **Unconfigured brands** get the clinical readout only — active issues with type,
  severity, counts, and dates. No "Elevated", no invented score.
- **Configured brands** get their own labels when their own thresholds fire. The tier
  rule vocabulary grows two rules to make issue-level triggers expressible:
  `active_issue_severity` (fires on an active issue at/above a severity) and
  `active_issue_types` (restrict to listed event types). Existing volume/sentiment rules
  are unchanged, so today's configurations keep working.

This retires the platform-invented 0–100 number and its 30/60 bands. The dashboard gauge
is replaced by an issue panel (severity-sorted active issues) plus the attention readout.
The narrative prompt's mandatory risk-assessment block references the issue list and
fired tier status — both deterministic — which removes the failure mode where prose
asserts a sentiment swing the data cannot support.

## Implementation decisions (added after review, 2026-08-14)

**Issue identity and merging.** A screened article joins an existing issue when, for the
same brand: (a) it shares a `bw_article_stories` group with an issue member, or (b) the
cheap-LLM confirmation says so for the best embedding candidate. Embedding similarity
(title+summary, per the CE-tier lesson that title-only is unreliable) NOMINATES
candidates; it does not merge. This was a measured correction to the first draft
(0.85 auto-merge): on wbm's live corpus, two genuinely distinct events ("Physicist
fired over publishing scam" vs "Courant editors leave Wiley") score 0.982 — as high as
same-story pairs — so same-topic and same-story are inseparable by similarity on the
768-d encoder, and the first build merged the bribery investigation into a
Glassdoor-seeded issue at 0.899. Tuned values: auto-merge only at ≥ 0.99
(near-duplicates; syndicated copies are already caught by story groups), LLM
confirmation decides the 0.85–0.99 band, below 0.85 founds a new issue. The
confirmation prompt states both directions: different events on the same broad topic
are NOT the same issue; a recurring stream of the same signal (e.g. employee reviews on
the same themes) IS one continuing issue. Thresholds remain config values, re-tunable
on the calibration fixture. False merges and splits are corrected by analyst action
through the finding-review pattern (`bw_finding_reviews` precedent): a stored
split/merge override that the issue builder respects on every rebuild, so corrections
survive recomputation.

**Historical semantics.** The endpoint evaluates active-ness **as of the `end`
parameter**, never as of today: an issue is active at `end` if its last coverage falls
within its severity-scaled expiry window before `end`. A report regenerated for July
therefore shows July's issue state, calibration runs reproduce exactly, and the live
dashboard is simply `end = now`. All stored verdicts carry `model` and `prompt_version`,
so a historical evaluation can state which screener produced its classifications.

**Peer eligibility, precisely.** A "scored peer article" is a row joined to the peer via
`bw_article_categories` with `COALESCE(bac.relevance_score, a.topic_alignment_score)
>= 0.4`, non-empty sentiment, counted `DISTINCT ON uri`, publication date inside the
window. A peer is eligible when it has ≥20 such articles in the window; the sector-wide
annotation requires ≥2 eligible peers. Cross-brand story matching reuses the issue
matcher (same embedding + confirmation path) run against eligible peers' screened
coverage in the same window.

## Calibration and regression

Calibration is an executable fixture, not a judgment call:

- **Labeled fixture**: a checked-in file (`tests/fixtures/brand_risk_fixture.json`)
  listing ground-truth events — the 9 wbm incidents plus the known external events —
  each with expected event type, expected severity, the article URIs that must group
  into one issue, plus a set of ordinary brand-weeks expected to produce nothing above
  medium. Labels authored by Oliver with session support, which is itself the severity
  rubric review: the rubric (one paragraph per severity level per event type) is
  written into the screening prompt, and disagreement with a label means the rubric or
  the label changes before any threshold tuning.
- **Pass criteria**: every ground-truth high event yields exactly one active
  high-severity issue of the expected type at its as-of date; multi-week stories merge
  to one issue (no duplicate issues for the same event); no ordinary fixture week
  produces an issue above medium; grouping precision on the labeled URIs ≥ 90%.
- **Versioned**: fixture results are recorded against `model` + `prompt_version`. Any
  later prompt, threshold, or model change reruns the fixture and must keep the pass
  criteria; the fixture is the regression suite.

## Architecture

One server-side module, one endpoint:

- `app/services/brand_screening.py` — screening (extracted from
  `brand_watcher_routes.py`), writing `bw_screening_verdicts` + `bw_article_risks`.
- `app/services/brand_risk_assessment.py` — issue builder + assessment reader.
- `GET /api/brand-watcher/brands/{brand_id}/risk?start=&end=` returns active issues as
  of `end` (typed, severed, with justifications and peer-context flags), the attention
  readout, and the fired escalation tier if any. No score field.
- Dashboard, PDF export, and narrative all consume this endpoint. `computeBrandRisk`
  (BrandWatcherTab.tsx) and `bwComputeRisk` (exportService.ts) are deleted.
- New tables via Alembic: `bw_screening_verdicts`, `bw_issues`, `bw_issue_articles`
  (join), `bw_issue_overrides` (analyst merge/split corrections).
- LLM use is confined to screening verdicts and issue-merge confirmation, cheap-model
  only, per-flagged-article not per-article. Everything the customer sees is
  deterministic given those stored verdicts.

## Rollout

Canonical bugfixing first; the calibration fixture must pass before any customer tenant.
Then wbm, wileytest, abm, ibaset, bwtemplate by the standard copy + Alembic + restart
procedure (pre-restart agent/tracker checks, per-tenant alembic head checks before
copying migrations). wiley prod ships for parity (zero brands, no-op). pearson stays
excluded until its general catch-up. UI via `./ui/deploy-react-ui.sh` + rsync. The old
score's surfaces (gauge, PDF section, narrative block) switch over in the same release
so the two vocabularies never coexist; rollback is the previous deploy of the same
files, and a pre-rollout snapshot of one tenant's rendered report is kept to diff a
rollback against.

## Out of scope

- Changing the sentiment model or category vocabulary.
- Backfilling sentiment onto pre-April articles.
- Repairing/backfilling `bw_daily_stats` (optional follow-on; Attention does not
  depend on it).
- Flagship-model or per-article LLM scoring (cost rule stands).
- The saas tenants — Brand Watcher is monolith-only.
- Impact quantification (financial exposure per issue). The severity rubric is
  qualitative low/medium/high; anything finer is a later conversation with customers.

## Effort (AI sessions, revised after review)

1. Screening extraction + coverage extension + verdict table + historical screening
   backfill over the ~17-week corpus: ~2 sessions.
2. Issue tables + grouping + overrides + assessment endpoint + escalation-tier rules:
   ~1.5 sessions.
3. Fixture authoring (with Oliver), rubric, threshold tuning, calibration runs: ~1.5
   sessions.
4. UI issue panel + attention readout + PDF + narrative switchover, delete client
   copies, tenant rollout with migrations and rollback check: ~1.5 sessions.

Total ~6.5 sessions. The original 4-session estimate omitted the backfill, threshold
tuning, migrations, and rollback validation.

## Decisions (Oliver, 2026-08-14)

1. **The 0–100 gauge is retired outright.** No derived number in the UI, reports, or the
   API. The issue panel + attention readout replace it everywhere.
2. **Taxonomy extends to eight event types.** Verification showed seven already exist in
   code; product_safety is the only addition.
3. **Issue expiry is severity-scaled**: 28 days (high) / 14 (medium) / 7 (low) without
   new coverage, with reopen-on-return.
4. **Peer "sector-wide" annotation is customer-facing where the peer corpus supports
   it** (≥2 eligible peers; wbm and wileytest today), computed but omitted elsewhere.
