# SaaS pricing: three plans, grounded in measured unit costs

**Date:** 2026-08-11
**Scope:** saas.aunoo.ai /pricing page — streamline four draft plans down to three, and decide whether coverage checks and deep-research queries need per-plan limits.
**Data source:** `llm_usage_log` on the `aunoo_saas_prod` database, last 30 days, costs recomputed from token counts at current Bedrock rates. The logged `cost_usd` column undercounts: Haiku rows are priced at a stale rate and some Sonnet rows (the `global.` profile and all claim-validation rows) log as $0 because the pricer never matched them.

## What each metered action actually costs us

| Action | True marginal cost | Why |
|---|---|---|
| Coverage check | ~$0.0001 | One embedding plus a pgvector query; the verdict is computed inline with no LLM call (`app/analyst/query_routes.py` in saasmvp-app) |
| Deep-research query | ~$0.01 typical, ~$0.08 for the heaviest playbook (consensus) | Sonnet, a few thousand tokens per call |
| Claim validation | ~$0.02 | Three Haiku stages (extract, web evidence, verify), ~11k prompt tokens total |
| Correspondent run | ~$0.042 | 1,345 runs in 30 days cost ~$56 in Haiku/Sonnet calls |
| Newsletter issue | ~$0.16 | Writer + sections + deep dive |

A correspondent therefore costs **$0.18/month on weekly runs, $1.30/month daily, $30/month hourly**. Run frequency is the only per-user lever that can meaningfully hurt margin. The items on the "to consider" list (coverage checks, deep research) are noise by comparison.

## The two open questions

**Coverage checks: don't limit them, and do mention them.** "Unlimited coverage checks on every plan" costs effectively nothing and reads as generosity. Put a fair-use rate limit in the ToS (a burst limit per minute) to stop scripted API abuse, but keep it off the pricing page.

**Deep-research queries: unlimited on paid plans, a generous visible cap on Free.** Even heavy use is pennies, so the cap is not cost protection — it is abuse protection (free accounts have no payment friction) plus an upgrade nudge. 25/month on Free, unlimited on both paid tiers.

## The streamlined three plans

Cut Studio and move newsletter generation down into Reader Pro. A weekly newsletter costs ~$0.65/month, so it is a cheap way to strengthen the mid-tier, and brand monitoring stays as Newsroom's clean differentiator — which is how the draft already positioned it.

| | Reader — Free | Reader Pro — $9X/user | Newsroom — $14X+/user |
|---|---|---|---|
| Topics | Unlimited (catalog) | Unlimited | Unlimited |
| Correspondents | 1, weekly | 5, weekly/daily | 25, up to hourly |
| Newsletter generation | — | Included | Included |
| Brand & entity monitoring | — | — | 10 brands |
| Claim validations | 10/mo | 25/mo | 100/mo |
| Deep research | 25/mo | Unlimited | Unlimited |
| Coverage checks | Unlimited | Unlimited | Unlimited |

Worst-case cost per user: Free ≈ $0.90/month, Pro ≈ $8/month (five daily correspondents plus a newsletter plus validations) — both comfortably inside their price points. Do not give Free hourly runs, or unrestricted daily on multiple correspondents: the draft's "weekly/daily/hourly" wording on Free would let one free user cost $30/month.

Claim-validation caps (10/25/50/100 in the draft) cost us $0.20–$2 per user at the limit. They are value metering, not cost metering, and the numbers can move freely.

## Two flags outside the grid

1. **"Unlimited topics" is only safe if it means the shared catalog.** The topic pipeline (classification, narratives, consensus, horizons, emerging topics, editorial) runs ~$1,050/month across today's 39 topics — roughly **$27 per topic per month**. Following an existing topic costs ~$0 marginally because tenants share the corpus, but if any plan lets users create *private* topics, that needs its own limit — for example custom topics as a Newsroom feature or a paid add-on.
2. **Newsroom's 25-correspondents-hourly ceiling is $750/month per user.** Realistic usage is far lower, but either price Newsroom knowing that ceiling exists, or cap hourly scheduling to a handful of correspondents (say 5 hourly, the rest daily) so the worst case stays under the price.

## Cost-reduction headroom (adjacent, no change requested)

The two biggest platform cost lines are `topic_classifier` on Llama 3.3 70B (~$300/month, 328k calls) and the newsfeed `incident_tracking` prompts on Haiku (~$220/month at 12.6k average prompt tokens). If the free tier ever needs margin headroom, those two lines are where it is.
