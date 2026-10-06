# Brand relevance: implementation specification

_Adopted 2026-10-06. Replaces the 2026-10-06 draft (`ffd1249a`). Scope confirmed by Oliver on
2026-10-06: every monolith site on the shared brand-news path, wileytest included. Appendix A holds
the deployment inventory; Appendix B the build and rollout plan; Appendix C the progress log._

Fix brand relevance in the shared monolith and carry the fix from bugfixing to every related tenant.
Genuine coverage must reach the right brand, sector stories and the brand's own content must remain
available without inflating press counts, and failed model calls must stay visible and retryable.

This is an implementation specification. The scope includes collectors, relevance decisions, stored
matches, every reader of those decisions, validation, tenant rollout and rollback. Sunstar and Oviva
supply reported examples; they do not limit the rollout.

## Scope and decisions

Bugfixing is the canonical validation site. Every related deployment using the shared brand-news path
is in scope, including future tenants. Before implementation, produce the actual deployment inventory:
site, source revision, database version, brand configuration, model route, enabled features and
deployment owner. A site with no active brands still needs migration and regression checks.

Apply the same coverage rules everywhere:

| Content | Where it appears | Counts as earned brand coverage |
| - | - | - |
| A story about the brand or a meaningful contribution by it | Brand press view | Yes |
| A genuine mention of the correct brand in a news headline | Brand press view | Yes |
| A relevant sector story with no meaningful brand involvement | Separate sector filter | No |
| The brand's own relevant content | Separate owned-content filter | No |
| A passing body mention | Available in broader topic results where appropriate | No |
| Wrong company, retail deal, fan recipe, unrelated or excluded content | Excluded from brand press | No |

A headline match must identify the correct company. Source and content exclusions still apply. A
recipe page or shop listing does not become press because its title names a brand.

Keep theme, market and social scoring contracts intact. The separate SaaS implementation needs its
own compatibility work; this specification does not authorize replacing either repository's
architecture.

## Starting point

Start from the current canonical source and each tenant's deployed version. The reviewed monolith
snapshot is `644ceec6503131472c3ea4d92895432c638b5619` (on GitHub; not in the local canonical repo,
whose HEAD was `f9d3b33f` on 2026-10-06). Its brand relevance draft is a starting point for the shared
change.

Preserve and verify the existing integrity fixes and decision reuse. Patch remaining gaps rather than
recreate working features. This specification replaces the draft's Sunstar-and-Oviva-only rollout,
automatic historical resweep and large mandatory annotation programme.

The reported Sunstar restores and stock-valuation reversions remain historical decisions. Deployment
must not undo them.

## Brand identity and collection

Use one effective brand profile for collection, mention detection and every model route. It contains
a stable brand identifier, canonical company identity, names and aliases, products, original-language
names, context needed for ambiguous names, exclusions, owned domains and the existing non-press rules.

Use `bw_brands` and its existing keyword/configuration fields where possible. Generic defaults may
fill absent fields; they must not overwrite explicit tenant rules. Record a normalized profile version
so changes can invalidate future decision reuse.

Resolve a topic to one enabled brand profile within its tenant and group. Display names are not
unique identifiers. Multiple matching enabled profiles must produce a visible configuration error and
an undecided candidate; do not merge their aliases or select the first row.

Match the original title, available summary and article text. Normalize Unicode consistently and
support Japanese and other non-Latin names without applying English word boundaries to them. Short or
common aliases need the configured company context. Literal matching confirms that a name occurs; it
does not by itself prove which company the article means. Resolve known collisions with evidence and
leave unresolved identity cases undecided. Record the matched alias, evidence field and a short
evidence extract. A search query or a provider's claimed match is collection evidence, not proof that
the article mentions the company.

Collectors must use the configured company names, products and language variants. Keep query
provenance and pagination/checkpoint behavior. Deduplicate candidates without discarding their topic
and keyword associations.

Fix the reported collector defects with captured payloads:

- Phantom matches must retain the provider query and show whether the returned content actually
  supports the match. Apply the topic's query semantics before presenting a verified brand mention.
- Retail deals, valuation pages and fan content must follow the existing intended source/content
  rules. Add positive examples so ordinary reporting on the company is retained.
- Reddit mapping must preserve available author, permalink, publication time and engagement fields.
  Missing fields stay missing.

## Decision order

For each article and target brand, run these steps in order:

1. Resolve the scoped profile and the actual evidence available.
2. Apply entity-collision and existing source/content exclusions.
3. Determine whether the publisher is owned by this target brand.
4. Detect the verified company or product mention.
5. Reuse a valid decision for exactly the same inputs, if one exists.
6. If a brand mention is present, judge the article's relationship to the brand.
7. Apply the verified headline rule, save the scoped decision and expose its provenance.

Do not pay for a brand judge to decide an article with no verified mention. Route it through the
existing sector/topic rules where applicable; otherwise it is outside brand coverage. Absence of a name
is not enough to declare every article a sector story.

Ownership is relative to the target brand. A publisher can be owned content for one brand and
independent coverage of another. Use configured owned domains and existing EntityIntelligence domain
identifiers, preserving supported legacy ownership tags. Match domain boundaries correctly; do not
trust arbitrary URL substrings or content instructions.

A correct company name in a genuine news headline guarantees coverage after exclusions. The judge may
distinguish subject from notable, but cannot demote it to passing or other merely because the body is
unavailable. If a conclusive headline or exclusion rule settles the decision, persist that rule
decision with its evidence and provenance even if a separate model attempt fails; do not fabricate a
successful model verdict.

A title-only item with a verified headline mention enters the judge using its title. Store and display
that limited-evidence status. Neither the prompt nor the saved reason may invent body content. An item
with insufficient evidence and no qualifying headline follows the existing enrichment-failure path,
remaining visible for retry.

## Relationship labels and model contract

The brand judge returns a category and a short reason:

| Label | Meaning | Earned inclusion for an independent eligible source |
| - | - | - |
| subject | The brand is a main subject of the story | Include |
| notable | The brand has a meaningful role, quotation, action or comparison | Include |
| sector | Relevant market coverage without meaningful brand involvement | Exclude from earned counts |
| passing | Incidental body mention | Exclude from earned counts |
| other | Unrelated, wrong entity or otherwise outside the coverage rules | Exclude |

Keep relationship and publisher ownership separate. A subject story published by the brand belongs in
owned content rather than earned press.

Categories express the coverage rules directly; they do not guarantee more stable model answers.
Measure repeatability on a bounded set with fixed evidence, profile, rubric and model version,
deliberately bypassing decision reuse only for that comparison. Report decision changes and failures.
Ordinary processing continues to reuse valid decisions. A reported score change is evidence to
investigate, not proof that every numeric approach or controlled rescore must fail.

The internal decision must match a strict schema: one allowed label and one nonempty reason. Each
provider adapter must first validate the provider's actual response contract, then construct that
internal result. Reject missing fields, unknown labels, malformed JSON and unsupported values. Apply a
bounded response size and existing timeout/retry limits. Article text is untrusted evidence;
instructions embedded in it cannot change the rubric or response contract.

A timeout, missing model, malformed result or exhausted fallback is an unavailable model judgment. It
is not a relevance score of zero, a rejection, or a successful model decision. Use the configured
fallback only through the same validation contract. If every route fails and no conclusive
deterministic rule applies, record the failed attempt and leave the candidate retryable.

For compatibility, the labels may map to existing numeric fields: subject 0.9, notable 0.7, sector
0.5, passing 0.2 and other 0. These numbers are compatibility grades, not probabilities. The category
determines brand inclusion. A numeric cutoff must not admit sector content or reject a valid
categorical headline decision.

Legacy numeric routes must validate finite numbers in the allowed range before coercion. Reject
booleans, NaN, infinity and out-of-range values. Handle supported decimal and scientific notation
consistently across local, LLM and Jev adapters.

## Storage and decision reuse

Extend the scoped `keyword_article_matches` record with nullable `brand_relation`, `judge_version` and
`source_relation`. The scoped `source_relation` is owned, independent or unknown for this article and
target brand; NULL belongs to legacy rows. New earned decisions require independent ownership
classification. A new unknown classification remains deferred. Keep existing decision status, score
and timestamp fields where they already serve the purpose, and retain evidence quality and provenance
in compatible storage.

The global `articles.bias_source` may remain a legacy display field, but it cannot determine ownership
for every brand. Brand readers must use the scoped classification. Test one URI that is owned for
brand A and independent coverage of brand B; its earned inclusion must differ correctly without
changing either brand's other decisions.

Keep three distinct outcomes: a valid included decision, a valid excluded decision and an unavailable
judgment. Unknown or corrupt stored labels must be surfaced as invalid and omitted from new earned
calculations; they must not fall back silently to a numeric score.

Rows with no new label retain their legacy decision until an explicit evaluation occurs. Preserve
operator overrides and restored historical decisions. A failed repeat must retain the previous valid
verdict and record the failed attempt separately.

Article and scoped-match updates must commit together wherever the operation changes both. A missing
target row or zero affected rows is a failed save. Preserve other brands' and groups' decisions and
all valid keyword associations.

Reuse both valid included and excluded decisions only when all decision inputs match:

- tenant, group/topic and canonical brand identity;
- the article evidence actually judged, including title-only versus enriched content;
- the effective profile and coverage policy;
- the rubric/prompt version and resolved model route/version;
- relevant source classification and explicit overrides.

A URI or display name alone is insufficient. A failed attempt is never a cached negative decision.
New or undecided candidates use the current inputs. Previously decided rows keep their verdict when
collectors rediscover them, even if the current profile, model or prompt differs. Changed inputs
invalidate reuse for an explicitly requested reevaluation; they do not authorize replacing an
existing verdict. Reconsidering decided rows, including after enrichment, requires a bounded repair
request or a deliberate operator action.

## Every consumer must use the same inclusion rules

Use one shared brand inclusion predicate in API and background readers. Apply it before pagination,
totals and aggregations. Article lists, filters and exports must agree with the counts they show.

Update the brand readers for article/category/time statistics, comparisons, share of voice,
sentiment, perception, narratives, digests and alerts. Earned metrics and earned alerts use eligible
independent subject/notable content. Sector and owned items remain separately accessible and clearly
marked.

Do not leave score-only queries such as `score >= 0.4` in brand calculations: the compatibility grade
for sector would pass them. Keep legacy fallback only for genuinely unlabeled rows.

Count a distinct article once per brand within the requested tenant/group/topic scope, even if
several keywords or categories match it. Preserve the product's existing cross-brand comparison
denominator and deduplication policy, documenting it in the metric response. One brand's decision must
not alter another brand's coverage.

The UI must show the relationship, ownership and limited-evidence/unavailable status where those
affect interpretation. Reader-facing explanations use plain language. Missing measurements display as
unavailable, not zero.

## Jev and model selection

Retain reversible per-tenant model settings and the existing fallback configuration. Do not switch all
tenants to Jev as a side effect of this change. Comparison calls and discovery experiments remain
opt-in, with explicit cost limits.

Every adapter receives the same effective evidence, profile and rubric and produces the same internal
decision contract. Prefer Jev Choice for the mutually exclusive relationship labels: it returns the
selected option, the option probabilities and confidence. The adapter must supply the internal reason
from actual match evidence when the provider does not return a rationale; it must not invent an
explanation. (https://docs.typesafe.ai/primitives/choice)

Jev Score is an expectation over ordered descriptive levels. Normalizing it does not turn it into
relevance probability. Noul answers one yes/no proposition; it does not measure degree of relevance.
A numerical rubric therefore needs an explicit mapping and separate validation before it can drive
these categories. (https://docs.typesafe.ai/primitives/score, https://docs.typesafe.ai/primitives/noul)

Pin an explicit supported model version and record the resolved model returned by the provider.
Validate expected question IDs and answer types, exact category keys, finite numeric values,
probability/confidence bounds and a probability sum near one using documented tolerances. The
selected Choice option must be one of the highest-probability options. A Score adapter must also
verify its level legend, range and weighted expectation. Follow the actual API schema rather than
requiring an invented success field. (https://docs.typesafe.ai/models, https://docs.typesafe.ai/api)

Authentication/request errors and missing or invalid answers remain unavailable judgments. Rate-limit
and transient-service retries use bounded backoff and the run's time/cost limits. Keep provider errors
separate from valid low relevance. (https://docs.typesafe.ai/api#errors)

Model disagreement means a case needs investigation. Agreement does not establish accuracy. Jev
confidence summarizes its returned distribution; it is not a guarantee of correctness. Do not display
confidence or category probabilities as measured AuNoo accuracy without domain evaluation. Include
ambiguous entities, adversarial article instructions and option-order changes in adapter validation.
(https://docs.typesafe.ai/confidence, https://docs.typesafe.ai/model-jaggedness/jev-1.13)

Model and threshold controls remain usable when there are no human labels. Configuration changes must
have an immediate rollback. An empty comparison run is inconclusive; it cannot report a win, 100
percent accuracy or a successful benchmark.

## Other hardening requirements

Apply these checks to all related tenant callers, including non-brand paths where the defect is shared:

- Pass effective group thresholds and supported request overrides through processing. Preserve the
  existing behavior of unrelated scoring paths.
- Preserve research inputs when scoring is unavailable; do not silently filter them out.
- Respect the status returned by called jobs. Failed, skipped and partial work cannot become a
  successful parent result.
- Advance checkpoints only after the associated durable writes succeed. Failed saves must leave work
  replayable.
- Bound retries, concurrency and per-run model spend; reuse decisions before calling a provider.
- Keep tenant/group scope in queries, caches and update predicates. Prevent concurrent workers from
  creating conflicting duplicate matches using existing database constraints or locking.
- Record model route, policy version, reuse/new-call status, failure reason and resulting inclusion.
  Keep secrets and unnecessary full article text out of routine logs.

Verify already shipped protections with focused regression tests. Do not introduce a separate scoring
service, mandatory ledger or broad database rebuild solely to deliver these fixes.

## Validation without a large annotation project

The agreed targets are precision and recall of 0.90: at least 90 percent of included items should be
genuine coverage, and at least 90 percent of genuine coverage in the evaluated candidate population
should be retained. These are separate measures, not a single accuracy score or a guarantee of finding
every published story.

Start with 20 reviewed rows per distinct brand identity and coverage policy as a diagnostic check.
Reuse an existing reviewed set across tenants when the company identity and rules match. Targeted
extra review is needed only for a different policy, ambiguous identity, language gap or a failing case.

There is no mandatory fresh set per tenant and no hundreds-of-clicks gate on operational fixes or
model controls. Shared automated fixtures and known reviewed examples support rollout. If there are no
reviewed examples for an accuracy claim, show that the measurement is unavailable.

The review question is plain: does this article belong in independent coverage of this brand? Also
record sector, owned and cannot-tell cases so failures are not forced into yes/no answers. Include
accepted and rejected candidates, headline and body mentions, limited text, original-language aliases,
collisions, owned sources and excluded sources. Record how rows were sampled; use population weights
when estimating rates from deliberately uneven samples.

Report true positives, false positives, false negatives, sample support and unavailable judgments.
Precision is TP/(TP+FP); recall is TP/(TP+FN). A missing denominator is unavailable. Report decision
availability separately and show how failures affect end-to-end coverage rather than dropping them
from the report.

Recall measured on collected candidates does not measure stories the collectors never found. Check
discovery coverage separately using known missed stories or an explicitly sampled discovery set. Do
not label model-produced answers as human ground truth.

Twenty rows expose obvious mistakes; they do not prove 0.90 performance across production. Replaying a
fixed reviewed set checks regression on those examples; it must not be presented as the current week's
feed accuracy or collection coverage. A claim about current production requires a suitable reviewed
sample from the stated period, with its sampling method and uncertainty. That review is required for
the claim, not for routine operation or access to model controls.

Show uncertainty and the population covered. If measured results miss the target, investigate before
enabling the changed automatic decision path for that affected configuration. Review and a recorded
rollout decision replace a rigid automatic benchmark lock.

## Required acceptance checks

| Area | Passing behavior |
| - | - |
| Scope | Bugfixing and every inventoried related tenant have a recorded compatibility and rollout result |
| Identity | Ambiguous names and duplicate profiles defer; multilingual and product aliases resolve with evidence |
| Headlines | Correct-company news headlines remain coverage, including title-only cases; collisions and excluded pages do not |
| Separation | Sector and owned content are visible separately and never inflate new earned counts or alerts; one URI can be owned for A and earned for B |
| Failure | Invalid/provider-failed judgments stay unavailable and retryable; a previous valid verdict survives |
| Reuse | Identical inputs avoid another paid call; changed content/profile/model does not reuse an incompatible verdict |
| Persistence | Failed/zero-row saves fail the job, preserve scoped associations and do not advance checkpoints |
| Consumers | Lists, exports, totals, narratives, digest and alerts apply the same rules without duplicate joins |
| Controls | Model selection works with no labels; route and feature rollback restore the prior behavior |
| History | Migration, startup, profile edits and rollout perform no automatic historical rescore |

Use captured failing examples and representative positives as regression fixtures. Include the
reported Sunstar multilingual/headline misses, ordinary independent company reporting, Oviva-owned and
sector content, fan recipes, phantom search matches and incomplete Reddit payloads. Carry fixtures to
canonical validation rather than requiring bugfixing to have the same live brands.

Run schema migration and API/background/UI contract tests, strict-parser/provider-failure tests,
scoped persistence/reuse tests and the relevant existing suite. Then run a per-tenant configuration
smoke check and one representative collection cycle during implementation rollout.

## Rollout and historical repair

Ship a compatible database migration before enabling label-aware writers/readers. Keep legacy rows
readable and categorical decisions disabled until the shared checks and tenant configuration review
pass. Package backend, migration, API contract and UI changes together. Preserve tenant-specific
features; older sites need a compatible patch rather than an unrelated wholesale replacement.

Validate on bugfixing first. Then enable one representative affected tenant, inspect a collection
cycle and expand in stages across the full inventory. Record revision, migration version, effective
profile/model and validation result for each site. Newly provisioned tenants must receive the same
contract.

Observe decision failures, deferred identities, unavailable rates, earned/sector/owned counts,
duplicate counts, reuse rate, new model calls, cost and latency per tenant. Stop expansion on a broken
contract, unexplained lost decisions or cross-scope updates. Rollback must restore the previous
route/read behavior while preserving stored labels and decisions.

Historical repair is a separate action. Prepare a bounded list of article-brand rows with old and
proposed decisions and reasons, review the changes, then use a controlled job with rate limits, stop
controls and recoverable before-values. Never rescore old verdicts automatically because a model,
prompt, profile or deployment version changed.

Completion requires a passing shared implementation, compatible readers and configuration on every
inventoried tenant, demonstrated rollback, and a documented result for the known failure cases.
Accuracy claims require measured support; operational completion does not require a new annotation
programme.

---

## Appendix A. Deployment inventory (2026-10-06)

Read from each site's tree, database and `.env`. "Brand news" = news rows on `Brand Monitoring %`
topics submitted in the last 30 days. "Verdict columns" = `keyword_article_matches` has
`relevance_status`, `topic_alignment_score` and `scored_at` (migration `rel_001`). Tenant git HEADs are
not a reliable source revision: sites are deployed by copying files, so most trees report the stale
HEAD `3b383f7c` while running newer code. Per-site source state is established by a file-by-file
comparison against canonical at rollout time (Appendix B, step R0).

| Site | Service | Tree HEAD | Alembic | Enabled brands | Brand news | Verdict columns | Mention gate | Model route |
|---|---|---|---|---|---|---|---|---|
| bugfixing (canonical) | active | f9d3b33f | mf_001 | 66 | 25 | yes | yes | default; Jev accept on |
| wileytest (Wiley prod) | active | 8ea95baf | si_001 | 4 | 5,897 | yes | no | default |
| wbm | active | fadee135 | vp_001 | 5 | 4,768 | no | no | default |
| oviva | active | 3b383f7c | mm_032 | 9 | 941 | no | yes (floor 0.5) | default |
| abm | active | 3b383f7c | mf_001 | 9 | 940 | yes | yes | default |
| sunstar | active | 3b383f7c | mm_032 | 5 | 913 | no | no | default |
| panaya | active | 3b383f7c | mm_032 | 7 | 0 | yes | no | default; Jev accept on |
| wiley | active | 9d05f5cb | si_001 | 0 | 0 | yes | no | default |
| abbott | inactive | 3b383f7c | tl_001 | 8 | 0 | no | no | env encrypted |
| bwtemplate | inactive | 3b383f7c | kg_lang_001 | 0 | 0 | no | no | env encrypted |
| helpnet | inactive | d048c3d2 | bw_005 | 0 | – | no | no | env encrypted |
| ibaset | inactive | 3b383f7c | bwr_001 | 5 | 0 | no | no | env encrypted |
| interroll | inactive | 3b383f7c | bwr_001 | 14 | 0 | no | no | env encrypted |
| opendemo | inactive | 68fb7619 | ti_001 | 3 | – | no | no | env encrypted |
| pbm | inactive | 3b383f7c | tl_001 | 4 | 0 | no | no | env encrypted |
| pearson | failed | 3b383f7c | emb_002 | 4 | – | no | no | env encrypted |
| sage | inactive | 3b383f7c | emb_002 | 4 | – | no | no | env encrypted |
| skunkworkx | inactive | e99a5495 | ti_001 | 1 | – | no | no | env encrypted |
| vc | inactive | c5b8ff71 | bw_005 | 1 | – | no | no | env encrypted |

Deployment owner for every site: Oliver Rochford. Wiley's rules apply on wileytest and wiley: no Jev
(per-site model choice stays as it is), and bulk jobs need Oliver's go.

## Appendix B. Build and rollout plan

### How the code works today (read 2026-10-06)

- **Brand topics are keyword groups** whose topic is "Brand Monitoring X" or "X - Brand Watch"
  (`hybrid_relevance_service.brand_name_from_topic`). `keyword_groups` has no brand id; the topic name is
  the only link to `bw_brands`, so a duplicate display name must defer, not merge.
- **Ingest** (`automated_ingest_service._process_single_article_async`) scores twice: a quick check on
  title and summary, then a full rescore after the AI analysis step, and approves on `score >= threshold`.
  Oviva's `brand_mention_gate.apply` rewrites the brand score afterwards (non-press, same-name, mention floor).
- **Per-topic verdicts** live on `keyword_article_matches` (one row per article and group, unique on
  `(article_uri, group_id)`), written by `async_db.record_group_relevance` (migration `rel_001`).
- **Brand Watcher readers** do not read those verdicts. A classification pass (`brand_watcher_routes`,
  `_run_brand_tracker`) selects analysed articles from every topic whose title, summary, tags or keywords
  name the brand, removes social posts and globally tagged owned publishing (`earned_news_sql`), and fills
  `bw_article_categories`. About forty readers join that table. Digest, alert, risk and narrative paths read
  the brand topic directly with score cut-offs (`topic_alignment_score >= 0.4`).

### Design decisions taken in the build

- **Where the label lives.** `keyword_article_matches` gains `brand_relation`, `source_relation`,
  `judge_version`, `decision_evidence` (JSON: alias, field, extract, evidence quality, provenance, reason,
  route, resolved model, profile and rubric versions, input key, collection query) and `last_failure`
  (JSON, failed attempts recorded apart from the verdict). Migration `br_001` also adds the `rel_001`
  columns where a site lacks them, so one migration serves every site.
- **What each label does at ingest.** subject/notable + independent: approved, earned. sector (any
  source), and owned subject/notable: approved so the row is analysed and visible, but never earned.
  passing and other: `filtered_relevance` with the label kept. Same-name collisions and exclusions:
  `filtered_relevance`, label `other`, provenance `rule`. No verified mention: the existing topic scorer
  decides; relevant becomes `sector`, otherwise `other`; no brand-judge call is made. Unavailable judge
  with no conclusive rule: `relevance_check_failed` (the existing retry path), failure recorded.
  Duplicate profiles, unresolved identity, unknown ownership of an otherwise-earned item: status
  `deferred` on the match row, article left undecided.
- **One decision per article and brand.** The brand path decides at the quick check and the post-analysis
  rescore reuses that decision; it never makes a second paid call.
- **Reuse.** A match row that already carries a valid label, or a legacy verdict, keeps it when collectors
  rediscover the article. Undecided rows (no verdict, failed, deferred) are decided with current inputs.
  A decision for the same article and brand in another group is copied only when the input key matches:
  canonical brand id, evidence hash and quality, profile version, policy and rubric version, resolved
  route, source relation and overrides.
- **The shared reader rule** (`app/services/brand_coverage.py`). A label veto: a row whose scoped match
  in the brand's own topic carries a label is earned only if it is subject/notable and independent;
  unknown labels count as invalid and are excluded. Unlabelled rows keep the reader's legacy condition.
  The classification pass also admits labelled earned rows that the name filter misses (body mentions,
  original-language names). Sector and owned items get their own endpoint and UI filter.
- **Flags.** `BRAND_RELATION_DECISIONS` (default off) switches the ingest path. `BRAND_PROFILE_COLLECTION`
  (default off) adds profile names and products to the brand groups' collection queries. The reader rule
  is always on but is a no-op until labels exist, and it checks the columns exist so code copied ahead of
  the migration cannot break a site. Model route: `BRAND_JUDGE_ROUTE` = `llm` (default, the site's
  `HYBRID_RELEVANCE_LLM_MODEL`) or `jev` (Jev Choice, opt-in).

### Phases

- **B1 Storage.** Migration `br_001`.
- **B2 Profile and mention check.** `app/services/brand_profile.py`.
- **B3 Decision path.** `app/services/brand_decision.py` and the ingest integration.
- **B4 Readers.** `app/services/brand_coverage.py`, the classification pass, digest, alerts, risk,
  narratives; sector and owned endpoint.
- **B5 UI.** Relationship, ownership and limited-evidence markers; sector and owned filters.
- **B6 Collectors and hardening.** Profile-driven queries, query provenance, valuation-page rule, reddit
  field check, checkpoint and status propagation audit.
- **B7 Validation.** Fixtures from the reported cases; review-sheet and metrics script.

Rollout, per site and in this order: R0 file comparison against canonical and patch plan; migration;
code with the flag off; smoke check; flag on; one collection cycle inspected; result recorded in
Appendix C. Order: bugfixing, sunstar, oviva, abm, wbm, wileytest, panaya and wiley, then the stopped
sites (migration and regression only while stopped).

## Appendix C. Progress log

| Date | Step | Result |
|---|---|---|
| 2026-10-06 | Spec adopted, inventory taken | This document |
| 2026-10-06 | B1 storage | `br_001` on canonical; upgrade, downgrade, upgrade clean (`d43c27a5`) |
| 2026-10-06 | B2 profile and mention check | `brand_profile.py`, 33 tests (`d43c27a5`; boundary fix for Latin names inside Japanese text in the B7 commit) |
| 2026-10-06 | B3 decision path | `brand_decision.py`, `brand_decision_store.py`, ingest wiring behind `BRAND_RELATION_DECISIONS` (`2b87a341`) |
| 2026-10-06 | B4 readers | `brand_coverage.py`; classification pass, 18 `_EARNED_NEWS` readers, risk, 5 sentiment alert/digest queries, coverage-split endpoint (`bfbf9771`) |
| 2026-10-06 | B5 UI | Coverage breakdown panel in the Articles tab; UI rebuilt (`a5595cf2`) |
| 2026-10-06 | B6 collectors and hardening | Profile keyword sync script, query provenance, brand-judgment retries, per-run judge budget, partial check status (`c87849d3`) |
| 2026-10-06 | B7 validation | Captured fixtures from sunstar/oviva (12 tests), reviewed profile additions for sunstar and oviva, additive apply script, review-and-metrics script |
| 2026-10-06 | Rollout prep | 13 versions of the ingest service across 18 sites: brand path moved to `brand_ingest_hooks.py`, inserted by `scripts/brand_rollout/transform_ingest.py` (all required anchors match on all 18); canonical rebuilt the same way (`cea85466`). Alert-query and keyword-monitor transforms; `deploy_site.sh`; `build_site_ui.sh` |
| 2026-10-06 | R bugfixing | Validation by fixtures (its two brand groups are social-only, so no live brand news). Restarted 12:02, flag off, health 200, no startup errors |
| 2026-10-06 | R sunstar | Code deployed (backup `/var/tmp/brand_rollout/backup/sunstar-20261006_120226`), `br_001` (mm_032 → br_001), reader counts scoped = legacy for all 5 brands with flag off, 58 profile additions (config only), 15 search terms, UI from its 2 Oct source tree (base hash reproduced), brand-retry cron every 30 min, **flag on**, restarted 12:04:49. Awaiting the first collection cycle (brand groups due 13:43–13:58) |
| 2026-10-06 | R oviva, abm, wbm, wileytest, panaya, wiley | Code deployed with the flag off (backups under `/var/tmp/brand_rollout/backup/`), `br_001` applied on each (oviva/panaya from mm_032, abm from mf_001, wbm from vp_001, wileytest/wiley from si_001), restarted 12:06–12:12 with no tracebacks, reader counts scoped = legacy on all 34 brands, UI with the coverage panel built from each site's own base (deployed hash reproduced first; only Brand Watcher and dependent chunks change). Flags stay off until sunstar's cycle is inspected |
| 2026-10-06 | Repeatability | `scripts/brand_judge_repeatability.py` on sunstar (route llm:nova-lite), 20 captured cases that reach the judge, 3 runs each with fixed evidence, profile, rubric and model, reuse bypassed: 0 label changes, 0 failed calls. All 20 are coverage-positive cases (the captured set has no body-mention negatives), so this shows stability on coverage, not on rejections; Oviva's own recipe pages read subject/notable and are kept out of earned counts only by the ownership check |
| 2026-10-06 | Sunstar human review | Oliver labelled 82 of 84 sampled articles (5 brands, 30-day window). Scored on the same rows, articles that never name the brand given their old verdict: old path 26 TP / 2 FP / 17 FN / 34 TN (precision 0.93, recall 0.60); new path 28 / 2 / 15 / 34 (precision 0.93, recall 0.65). New wins on Haleon (recall 0.45 to 1.00), Colgate and Lion; loses on Sunstar and Oral-B. The review found and fixed a regression added the same day: generic university words (students, campus, faculty...) in Colgate's context list marked a school oral-screening story as a different entity; replaced by colgate.edu and Colgate University. Lion gained the manga 3月のライオン and El Sistema (エル・システマ) as same-name collisions. Open policy questions from the answers: deal and product listings and automated valuation pages, which the spec excludes, were labelled coverage; oral-health articles that never name Sunstar were labelled Sunstar coverage, which the spec caps at sector |
| 2026-10-06 | Policy answers and rubric v3 | Oliver's answers to the three open questions: (1) a deal or product listing for the brand's own product counts as coverage ("it is advertising really"): no longer a rule exclusion; it goes to the judge and is marked `evidence.promotional` so readers can split it out; rubric brand-judge-3 says such a page is about the brand and a several-brand roundup is sector; (2) automated valuation pages stay excluded; (3) an article that never names the brand stays capped at sector. colgate.edu is a non-press site for Colgate. Scored under these answers (`brand_relevance_compare.py --policy`): old path 18 TP / 10 FP / 13 FN / 34+4 TN (precision 0.64, recall 0.58); new path 31 / 5 / 0 / 43 (precision 0.86, recall 1.00). All 5 new-path false positives are single-brand deal listings whose row answer (sector or not coverage) differs from policy answer 1. Sunstar restarted on v3 at 13:41 |
| 2026-10-06 | Sunstar first cycle; Oviva on | Oliver confirmed that every single-brand deal or product listing counts as coverage, so the five rows answered otherwise are reviewer inconsistency and the new path's Sunstar precision on the sample is 1.00 under the policy. Sunstar's first live cycle on v3 (Haleon group, 13:41-13:46): 21 decisions, no failures, deferrals or tracebacks; one admitted row pending its analysis. Oviva: `.env` backed up, `BRAND_RELATION_DECISIONS=1`, brand_retry cron every 30 minutes (no enrichment sweep there; dry run selected nothing), restarted 13:47 when quiet |
| 2026-10-06 | Oviva human review (partial) | Oliver answered 74 of 125 (Oviva, Voy, WeightWatchers, Second Nature complete; Numan 9/16, Juniper 1/16, HelloBetter and Noom none). Under the policy: old path 7 TP / 21 FP / 6 FN / 38 TN (precision 0.25, recall 0.54); new path 5 / 1 / 8 / 58 (precision 0.83, recall 0.38). The old path's 21 false positives are mostly general weight-loss stories that never name the brand. 7 of the new path's 8 misses are WeightWatchers recipe and meal-plan pages on ww-recipes.net and skinnytaste.com, which the profile lists as non-press sites but Oliver labelled coverage: open question. Fixed: Second Nature is an ambiguous name and now needs weight-loss context (a Harper's Bazaar fashion spread titled "Second Nature" was judged notable). Separately, Second Nature's Glassdoor data is for a Raleigh real-estate company of the same name |
| 2026-10-06 | Sunstar 14:10 check and two retry fixes | 98 decisions since the 12:05 switch-on: 1 unavailable (nova-lite returned JSON followed by extra text; strict parser, retried), 0 deferred, 2 pending. The unavailable one was RFE/RL's investigative unit "Systema", now a Lion same-name rule. The 2 pending were Haleon subject stories (Reuters, investing.com) whose collector gave no summary: the site's analysis reads only summary or content, so they failed as insufficient content although the page had been scraped. Fixes: `analyze_or_skip` analyses an admitted item without a summary from its scraped page (from the article or raw_articles), and treats it as headline-only when there is no text; `brand_retry` passed a `route` argument older ingest versions reject, so no cron retry had worked, and it now also retries admitted items whose analysis failed on cron sites (sunstar, oviva), counting each attempt against the cap. Both Haleon stories approved on retry with summaries from their pages |
| 2026-10-06 | Fan and recipe sites | Oliver chose the middle option for WeightWatchers recipe sites: kept as their own group, shown, never earned. New profile field `config.fan_domains` (version unchanged for profiles without it); a page from a listed fan site that names the brand is decided by rule as `sector` with `evidence.fan_content`, so the label veto keeps it out of earned counts and alerts; `coverage_split` reports it as bucket `fan`, and the Brand Watcher panel shows "Fan and recipe sites". On oviva, ww-recipes.net and skinnytaste.com moved from WeightWatchers' non_press_domains to fan_domains (row backed up to /var/tmp/brand_rollout/). The panel's "Not coverage" hint no longer names deal listings. Oviva UI rebuilt from its deployed tree (hash reproduced) plus /var/tmp/brand_rollout/patches/ui_coverage_fan.patch; later site UI builds need that patch after the panel patch. Existing rows are not rescored |
| 2026-10-06 | abm on | abm's enrichment sweep matched canonical except the brand-retry step (the sweep patch had not been applied at deploy); canonical sweep copied over, old file backed up under /var/tmp/brand_rollout/backup/, so abm needs no retry cron. `.env` backed up, `BRAND_RELATION_DECISIONS=1`, restarted 15:43 when quiet, no tracebacks. 9 brands, 18 active brand groups, no profile additions |
| 2026-10-06 | wbm on | Profile additions already applied; no enrichment sweep, so brand_retry cron every 30 minutes (dry run selected nothing). `.env` backed up, `BRAND_RELATION_DECISIONS=1`. An ingest run was in progress, so the restart waits for quiet (restart_when_quiet.sh, up to 45 minutes) |
| 2026-10-06 | wileytest on | Paying customer's site. Profile additions already applied; judge route stays llm (no Jev on Wiley sites); no enrichment sweep, so brand_retry cron every 30 minutes (dry run selected nothing). `.env` backed up, `BRAND_RELATION_DECISIONS=1`. An ingest run was in progress, so the restart waits for quiet |
| 2026-10-06 | panaya on | panaya has 7 brands but no brand-topic keyword groups (its brands are collected through the one topic "Market Monitoring Enterprise Test Automation"), so the decision path stays idle there. The flag's only effect is the alert and digest rule: the in-app alerts (11 in 30 days; email and webhook off) now draw on earned news only. `.env` backed up, flag on, brand_retry cron added for when brand topics appear, restarted 16:11 when quiet, no tracebacks |
| 2026-10-06 | Stopped sites | abbott, helpnet, ibaset, interroll, opendemo, pbm, pearson, sage, skunkworkx and vc lack helpers the new code imports (`async_db.build_enrichment_update`, `social_sources.earned_news_sql`) and several lack the Brand Watcher modules: they need a general catch-up before this contract can land. bwtemplate has every helper and can take the same deploy as the running sites. Not started |
