# Focus groups and extreme scenarios no longer come back empty on Kimi
_2026-09-10 · Explore → Focus Groups and Extreme Outlier Scenarios, all sites_

## What shipped
- A focus-group run that used to finish with zero personas on sites running Kimi K2.5 now produces its full set.
- Both generators keep whatever complete results they got if a model reply is cut short, and say so in the run's error list, instead of quietly continuing with nothing.
- The persona limit you set is respected: one persona per archetype, never more than you asked for.
- The stakeholder discovery step now sees each article's sentiment, category, bias and driver type. Before, it was handed "neutral" and "unknown" for every article.

## Why it matters
An operator ran a focus group and got an empty room: no stakeholders, no archetypes, no personas, and a green "success". The model had in fact written 42 stakeholder mentions before we cut it off at a fixed output limit, and our parser turned the cut-off reply into an empty list. The limit was set for terser OpenAI models. Kimi writes about ten lines per item, so it hit the limit on nearly every run.

Now the limit is high enough for the job, the reply is checked for the field each step needs, and a cut-off reply keeps its complete items. A run that still cannot be used stops with a reason the operator can read, rather than a confident empty result. On the internal site the same request that returned nothing now returns 60 stakeholder mentions, 3 archetypes and 8 personas.

The same guard covers all eight steps of the two generators, so the extreme-scenario builder gets the same protection.

## Release notes (copy-ready)
- Focus groups on sites running Kimi K2.5 now return personas. Previously the discovery step was cut short and the run finished empty.
- Extreme-scenario and focus-group runs record when a model reply was cut short and keep the complete items.
- Stakeholder discovery uses each article's sentiment, category and bias.
- The persona limit is enforced: one persona per archetype, up to the number requested.

## Demo / walkthrough
Explore → Focus Groups → pick a topic → Generate. The run should end with named personas. If a step's reply was cut short, the run's error list says which step and how many items were kept.

## Positioning notes
None. This restores a feature that had stopped working on Bedrock-backed sites.

## Limits and what's next
- Steps are allowed more time now, so a run takes longer than before on Kimi: about four minutes for a three-persona focus group on the internal site.
- The caps were raised, not removed. A very large or unusually verbose reply could still be cut; the run will then say so and keep what it has.
- Runs from before today were not re-run. A saved focus group with zero personas from before 2026-09-10 needs regenerating.
