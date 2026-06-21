# Opoint evaluation — €20k English feed (decision memo)

**Recommendation: Do not buy the €20k limited English feed as offered.**
At ~10× current spend it adds a thin slice of genuinely useful brand coverage, and the
signals that *would* justify it (for influence-ops detection) are not in this tier — some
don't exist in Opoint at all. Reconsider only if Opoint includes the premium signals below.

---

## 1. Cost

| | Annual | Note |
|---|---|---|
| **Opoint** | **€20,000** | limited English-language feed |
| Current (newsdata.io → newsfirehose) | **<€2,000** | drives our existing collection |

→ **~10× the cost.** It must deliver ~10× value or unlock a capability we can't otherwise get.

## 2. Content value — measured, quality-adjusted (4 brands, 12 months)

"Useful" = on-brand (entity relevance ≥0.4) **and** non-scholarly **and** incremental
(a source domain our existing feeds don't already cover).

| Brand | Raw Opoint articles | High-value incremental |
|---|---|---|
| Wiley | 1,275 | 88 |
| Elsevier | 1,594 | 100 |
| Pearson | 1,433 | 33 |
| SAGE | 750 | **0** |
| **Total** | **~5,050** | **221 (4.4%)** |

- **~95% of Opoint's volume is peripheral / citation noise** (journal/citation mentions, not brand news). The dominant filter is *relevance*, not dedup.
- **~221 usable items/yr ≈ €90 per usable article.** One tracked brand (SAGE) yields **zero**.
- What Opoint *does* uniquely add as enrichment: resolved entities (Wikidata), source country, source rank. Useful, but thin at this price.

## 3. Influence-ops / CIB detection fit (saas.aunoo.ai) — the key new question

Our coordinated-influence detection (`saasmvp-app/app/tasks/propagation_detection_task.py`)
runs two channels today: **near-copy** (DeBERTa embedding cosine ≥0.92 + 24h window) and
**shared-citation** (URL/quote Jaccard). The gaps it would want filled are: republication
*breadth* (how many outlets ran identical content), source country/reach, ownership/state
affiliation, and entity co-occurrence for rewrite-resistant matching.

Those are exactly the fields I checked against the live Opoint feed:

| Signal CIB detection needs | Opoint field | In our feed? |
|---|---|---|
| Coordinated republication count (N outlets, identical story) | `identical_documents.cnt` | ❌ **null** (verified live) |
| Cross-source spread / where else it ran | `sources[]` | ❌ **empty** (verified live) |
| Near-duplicate similarity | `almost_identical.sim` | ❌ **absent** (verified live) |
| Audience reach (amplification weight) | `similarweb` readership | ❌ domain only, **no numbers** |
| Source credibility / propaganda flag | — | ❌ **does not exist in Opoint** |
| Ownership / state-affiliation flag | — | ❌ **does not exist in Opoint** |
| Source country | `countrycode` | ✅ present (but we can derive this) |
| Source rank (reach proxy) | `site_rank` | ✅ present |
| Resolved entities (Wikidata) | `topics_and_entities` | ✅ present (needs `textrazor` param) |

**Conclusions:**
- The **#1 most valuable CIB signal — republication clustering — is null in this tier.** And we already compute that ourselves from embeddings, so even if present it would only save compute.
- **Credibility, ownership, and state-affiliation flags simply don't exist in Opoint** (the data dictionary confirms: no credibility/bias/propaganda flags). We already have MBFC (9,514 sources) locally for credibility and a state-media list.
- **SafeFeed is not a disinfo product** — it's a real-time content feed with the same metadata; no CIB/propaganda/credibility signals.
- The **one genuine marginal fit** is Opoint's resolved entities → our paused "narrative entity overlap" channel (rewrite-resistant detection). But we can also get entities from our own NER; it's a convenience, not a unique unlock.

→ **Opoint as offered does not enable the influence-ops detection we do under saas.aunoo.ai.**

## 4. The defensible one-liner

> At ~10× our current news spend, Opoint's limited English feed delivers ~220 genuinely
> incremental brand articles a year (~€90 each, zero for one brand), and the influence-ops
> signals that might justify it — republication clustering, cross-source spread, reach,
> credibility/ownership/state flags — are either license-gated, empty, or non-existent in
> Opoint. SafeFeed adds none of them. Not worth €20k as offered.

## 5. When to reconsider

Only worth re-opening if Opoint will include, and price competitively, the **premium signals**:
`identical_documents` clustering + `sources[]` spread + `similarweb` readership. Those *could*
feed the saas CIB pipeline — a different, defensible product story than "more brand articles."
Ask what those tiers cost vs. the €20k before walking away entirely.

*Evidence: live API tests + quality-adjusted analysis on the Wiley/Elsevier/SAGE/Pearson brand
corpora (wileytest), 365-day window. Reproducible via Brand Watcher → "Opoint vs Existing" tab.*
