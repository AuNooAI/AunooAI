# Issue: model names are aliases three layers deep, and it bit us on 6 Sep

_Status: for team discussion · Raised 2026-09-06 · Owner: TBD_

## Summary

The name a feature asks for is almost never the model that runs. Settings rows say
`gpt-4o-mini`, 84 source files default to `gpt-5.4-mini` or `gpt-5.4`, and a lookup
table in `app/config/litellm_config.yaml` quietly turns all of those into Claude Haiku 4.5
or Claude Sonnet 4.5 on Bedrock. Nobody chose Haiku for the emerging-topics detector, yet
that is what ran on every site, and when Bedrock's Haiku endpoint returned "unable to
process your request" on the morning of 6 September the daily run failed on sunstar and
bugfixing.

We can fix this. It has not been fixed because a wholesale change repoints every feature's
model at once, and our own rules say never do that without a before/after on the output.
This issue lays out the layers, what the fix would take, and the decisions the team needs
to make.

## What happened on 6 September

- 10:50 on sunstar: detection run 56 called `gpt-4o-mini`, which the yaml maps to
  `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0`. Bedrock answered
  `ServiceUnavailableError: Bedrock is unable to process your request`. The run was marked
  failed. Bugfixing hit the same error three times in the same window.
- Other Bedrock models were fine. Wileytest served 2016 calls on kimi-k2.5 and 4680 on
  nova-lite in the same half hour with no errors. The outage was Haiku-only.
- We recovered sunstar by writing `bedrock-kimi-k2-5` into `emerging_topics_settings.model`
  and re-running. Run 57 completed: 250 articles sampled, 6 topics, 198 seconds.
- Two of those six topics got a placeholder deep analysis because kimi's JSON reply was cut
  off at the analyzer's 2000-token cap. That is a separate, known problem with reasoning
  models and long JSON, noted here so it is not mistaken for part of the alias issue.

The immediate fix was one row on one site. Every other site still says `gpt-4o-mini` for
that feature and will hit the same failure the next time Haiku has a bad morning.

## The three layers

### Layer 1: the yaml alias table

`app/config/litellm_config.yaml` has 20 entries tagged `legacy_alias: true`. Twelve are
OpenAI names that never call OpenAI:

| Name asked for | Model that runs |
|---|---|
| gpt-4o, gpt-4.1, gpt-5, gpt-5.4, gpt-5.5 | Claude Sonnet 4.5 on Bedrock |
| gpt-4o-mini, gpt-4.1-mini, gpt-4.1-nano, gpt-5-mini, gpt-5-nano, gpt-5.4-mini, gpt-5.4-nano | Claude Haiku 4.5 on Bedrock |
| claude-3-5-sonnet-latest, claude-3-7-sonnet-latest, claude-4-sonnet-latest | Claude Sonnet 4.5 on Bedrock |
| gemini-pro, gemini-2.0-flash-exp, mixtral-8x7b | Claude (see yaml) |

`bedrock-claude-haiku` and `bedrock-claude-sonnet` carry the same tag, so even two of the
"honest" names are on the deprecation list. The table is re-read live, which is convenient
for hot repoints and is also why a repoint changes behaviour everywhere at once.

### Layer 2: hardcoded defaults in code

84 Python files under `app/` carry a literal gpt-* model name as a default argument or
fallback. The count by name:

| Literal | Occurrences |
|---|---|
| `gpt-5.4-mini` | 124 |
| `gpt-5.4` | 88 |
| `gpt-5.5`, `gpt-5.4-nano`, `gpt-4-turbo`, `gpt-4o-mini` | 3 each |

The heaviest files are `app/services/auspex_service.py` (31), the trend-convergence,
futures-cone and executive-summary routes (39 between them), and `news_feed_routes.py` and
`vector_routes.py` (17 between them). A model change today means touching each of these or
accepting that the yaml silently overrides them.

An earlier audit (see the LLM call-pattern notes) counted about 17 files that call a
provider directly and never consult the yaml, so for them the literal is the real model.
The rest send the literal through the yaml and get whatever the alias table says. That
figure was not re-measured for this issue. From the outside the two cases look identical.

### Layer 3: live settings rows on each site

Six settings tables hold a model choice that an operator can edit in the UI, plus a
per-topic default on `keyword_groups`. What they hold today:

| Site | Emerging topics | Keyword monitor default | News feed dashboard | Topics with a gpt-* default |
|---|---|---|---|---|
| bugfixing | gpt-4o-mini | bedrock-kimi-k2-5 | gpt-4o-mini | 0 of 6 |
| sunstar | bedrock-kimi-k2-5 (changed 6 Sep) | bedrock-kimi-k2-5 | gpt-4o-mini | 0 of 17 |
| oviva | gpt-4o-mini | bedrock-kimi-k2-5 | gpt-4o-mini | 0 of 11 |
| abm | gpt-4o-mini | gpt-4o-mini | gpt-4o-mini | 7 of 16 |
| wbm | gpt-4o-mini | bedrock-kimi-k2-5 | gpt-4o-mini | 9 of 22 |
| wiley | gpt-4o-mini | bedrock-kimi-k2-5 | gpt-4o-mini | 0 of 13 |
| wileytest | bedrock-claude-haiku | bedrock-kimi-k2-5 | gpt-4o-mini | 8 of 23 |

Bugfixing also has `geopolitical_schedules.model = gpt-4o-mini`. Every "gpt-4o-mini" in
that table is Haiku 4.5 in practice, the model our cost notes say to avoid. Abm's keyword
monitor default is Haiku on every article it enriches.

More than 40 further columns record `model_used` for provenance. Those are history and should stay
as written. `resolve_model_identity()` in `app/ai_models.py` already translates an alias to
the real model before logging, so the ledger is honest even though the settings are not.

## Why this matters beyond one outage

- **Cost decisions do not stick.** We decided on kimi for enrichment and nova for cheap
  tiers. Three tables and 24 topics still say Haiku by another name.
- **Outages hit the wrong features.** A Haiku problem took out emerging topics, a feature
  nobody knowingly put on Haiku.
- **Nobody can answer "what model does X use" without reading three places.** That includes
  the model dropdown in the UI, which filters on the `legacy_alias` tag and so hides the
  very names the settings rows contain.
- **Repoints are all-or-nothing.** Editing one yaml line moves every gpt-5.4-mini caller at
  once, which is why we have avoided touching it.

## Proposed fix, in stages

1. **Make the yaml the single source of truth.** Keep the concrete `bedrock-*` names as the
   only non-legacy entries. Add three tier names, for example `tier-fast`, `tier-standard`,
   `tier-premium`, each pointing at one bedrock model. Every gpt-* and claude-*-latest
   entry stays as a deprecated alias pointing at a tier, so nothing breaks on day one.
2. **Replace the 84 files' literals with one call.** A helper such as
   `default_model("fast")` that reads the tier from settings. Mechanical but wide. Needs a
   compile pass, the test suite, and a grep that proves no gpt-* literal remains outside the
   yaml.
3. **Migrate the settings rows.** One Alembic data migration that rewrites the six settings
   tables and `keyword_groups.default_llm_model` from alias names to tier names, on every
   site. Provenance columns are left alone.
4. **Choose the tier per feature, with evidence.** This is the only step with judgement in
   it. Anything customer-facing gets a before/after sample before it moves, per the
   content-quality rule.

Estimated AI effort for stages 1 to 3: half a day, plus a job-gated restart on each of the
7 active sites and a copy to bwtemplate. Stage 4 is open-ended and depends on how many
features the team wants to re-evaluate rather than just relabel.

## Decisions for the team

1. **Tier names or model names in settings?** Tiers let us swap the underlying model in one
   place. Model names are honest but put us back to editing 7 databases per change.
2. **Do we keep the gpt-* aliases at all after migration?** Keeping them protects any
   external caller or saved prompt we have forgotten. Dropping them removes the trap for
   good. A middle path is to keep them for one release with a startup warning.
3. **Which features get a real before/after in stage 4, and which just get relabelled?**
   The candidates are the ones whose output a customer reads: Auspex, briefings, reports,
   emerging topics, news feed highlights.
4. **What is the fallback rule when a Bedrock model is unavailable?** Today there is none
   for the scheduled jobs. A tier could carry an ordered fallback list in the yaml.

## What was done already

- 2026-09-06: sunstar `emerging_topics_settings.model` set to `bedrock-kimi-k2-5`; run 57
  completed on it. No code changed. No other site touched.

## Evidence

- Failing call: sunstar journal 2026-09-06 10:50:13, `app.ai_models - ERROR - Error
  generating with model bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0:
  litellm.ServiceUnavailableError`.
- Alias table: `app/config/litellm_config.yaml`, entries tagged `legacy_alias: true`.
- Literal count: `grep -rhoE "[\"']gpt-(4o|5\.[0-9]|4)[a-z0-9.-]*[\"']" app --include=*.py`
  on canonical at commit 61b88dff.
- Settings rows: queried per tenant database on 2026-09-06 with `sudo -u postgres psql`.
- Run records: `detection_runs` rows 56 and 57 on sunstar.
