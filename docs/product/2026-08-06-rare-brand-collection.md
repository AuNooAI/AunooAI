# Niche brand names now collect news reliably
_2026-08-06 · news collection for brand monitoring groups — all customer sites_

## What shipped
Searches for rarely-mentioned names — a niche vendor, a small competitor, a product with an
unusual name — could hang inside our news source until the collector gave up, so a monitoring
group built around such a name silently collected nothing. The collector now detects the hang
within 20 seconds and reruns the search a different way that always answers. Widely-covered
names are unaffected.

## Why it matters
Before: the customer whose own brand is a niche name got an empty brand column while the
big-name competitors next to it filled up — the worst possible shape for a brand-monitoring
product, and invisible because the system reported each run as successful. On the affected
site, the customer's own group had collected zero articles since setup.

Now: the same group collects. Its first successful run brought in the industry coverage that
names the customer, approved the relevant piece, and filtered the marginal one — the normal
behaviour every other group already had.

## Release notes (copy-ready)
- Fixed: monitoring groups for rarely-mentioned brand names could collect no articles at
  all. Searches that stall are now retried a different way within seconds.
- Groups tracking low-coverage brands can also be given a longer look-back window so
  existing older coverage is picked up on the first run.

## Demo / walkthrough
Gather page on the ibaset site: the "iBASEt - Brand Watch" group now shows collected
articles; Explore → News Feed at a 90-day range shows the approved industry coverage.

## Positioning notes
Brand monitoring for mid-market B2B customers depends on exactly these low-volume names;
"we cover the brands nobody else writes about daily" only holds if rare-term search works.

## Limits and what's next
- The underlying news source has little iBASEt coverage — two industry reports in ninety
  days. The fix makes what exists collectable and future coverage arrive; it cannot create
  coverage. Adding sector keywords to the group is the lever if the customer wants a fuller
  column.
- The slow search path is a service-side flaw in the news source's newest-first ordering;
  we route around it. Fixing it at the source would remove the 20-second first-attempt cost
  for rare terms.
