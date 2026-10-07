# Provider identity in observation keys: migration plan

Spec 08, WP7: "Observation provider can become the publisher domain." This is the plan for that
fix. Nothing here is built yet, and it ships separately from the other WP7 repairs.

## The problem

`article_identity.provider_of()` decides which provider a collected copy came from. It reads
`raw_data.provider`, then `raw_data.source_name`, then `article.provider`, and finally falls
back to `article.source`. For the firehose, `source_name` and `source` hold the publisher's
domain, so the publisher ends up recorded as the provider.

That name goes into the unique key for the copy (`article_observations.observation_key`):

- `provider_id:<provider>:<external id>` when the collector gives its own id;
- `canonical_url:<provider>|<url>` otherwise.

On bugfixing (`test`, 7 Oct 2026), 9,065 of the 13,478 observation rows (67%) are keyed by a
publisher name rather than a collector name. 8,514 of those are provider-id keys, for example
`provider_id:globenewswire.com:4975612`, where `4975612` is the firehose's own article id.
There are 1,296 distinct "providers", when the site runs about a dozen collectors.

This causes three problems:
- **Wrong provenance:** reports of which provider supplied an article name publishers.
- **Collisions:** two collectors whose numeric ids overlap, delivering the same publisher, get
  the same key. The second copy is then treated as a replay of the first.
- **Lost replays:** if the firehose renames a publisher, the same firehose article gets a new key
  and is stored as a new observation.

## The change

1. `provider_of()` prefers `article["collector_source"]`. The keyword monitor sets this field on
   every item it collects (`keyword_monitor.py`, `_search_with_collector`). After that it uses
   `raw_data.provider`. The current chain stays as the last fallback, for callers that set
   neither (manual submission, RSS imports, scripts).
2. New observations are written under the new key only.
3. Lookups try the new key first, then the legacy key computed with the old rule. That way an
   item collected before the change is still recognised as a replay, and nobody has to rewrite
   old keys.

## Why we leave old keys alone

The stored rows cannot tell us which collector produced them. `payload` carries only
`published_date` and `authors`, and `collector_source` was never stored. A rewrite would have to
guess, and a wrong guess merges two different articles' observations under the unique
constraint. Old keys stay as they are.

The dual lookup can be removed once no collector can return an item collected under the old
rule. That is the longest lookback (30 days) plus the catch-up gap windows, so in practice 45
days after deployment. Removing it is a separate one-line commit.

## Database changes

None are required, because the key column and its unique constraint stay the same. An optional
Alembic migration could add `article_observations.key_version smallint` (1 = legacy, 2 = new),
which would let health show the share of legacy keys falling over time. That is useful, but it
does not block the change.

## Tests to write first

- Two collectors returning the same numeric external id for the same publisher produce two
  observations, not one.
- An item stored under a legacy key, then collected again after the change, resolves to the
  existing article and does not insert a second observation.
- A firehose item whose publisher name changes between collections keeps one observation.
- Items without `collector_source` (manual, RSS) get exactly the key they get today.
- The unique constraint is never violated on replay, for news, social and RSS items.

## Rollout

1. Bugfixing first, after the WP7 release has run for a day.
2. Measure before and after: the number of observations per article; the share of new rows whose
   provider is a collector name, where the target is all new rows from the keyword monitor;
   and unique-constraint errors in the log, where the target is none.
3. Then roll out to the other sites, together with the ingest-spec migrations (`ip_001`–`ip_003`).
4. Rollback means reverting the commit. Old and new keys coexist, so no data needs undoing.

Estimated effort: about an hour of AI work, including the tests.
