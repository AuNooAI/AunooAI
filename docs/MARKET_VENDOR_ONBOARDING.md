# Adding a vendor to a market, fully

What it takes for a new vendor to reach parity with the established ones. Written
2026-09-02 after adding Eventus Security and D3 Security to market 2 from their
vendor-request form submissions and finding the form's add path covers only part
of the wiring. Reference vendor for "fully wired": Dropzone AI (brand 92).

## 1. The registry entry (the add-vendor route, or the same SQL)

`POST /api/market-monitor/markets/{id}/vendors` with a display name and website:

- `bw_brands` row — slug, display name, and `brand_keywords` built by
  `brand_keywords_for_vendor()` so an ordinary-word name doesn't match noise.
  Reuses an existing brand row by display name rather than duplicating it.
- `bw_market_brands` row — role `vendor`, next `sort_order`,
  `collection_enabled = TRUE`.
- A `domain` identifier in `bw_vendor_identifiers` when a website was given.
  **Always give the website.** The domain is the key almost everything
  automatic hangs off.

A vendor-request form submission (`market_vendor_requests`) does NOT do any of
this — it only records the ask and emails the operator. Someone still has to
approve and run the add.

## 2. What happens on its own after that (all keyed on the domain)

The market monitor's 10-minute tick seeds a `bw_entity_source_policies` row per
vendor per source (`seed_policies`, idempotent, every tick). Eligibility is
recomputed as identifiers appear. From there:

- **Site and feed discovery** — a collecting vendor never probed makes a
  discovery run due immediately (not waiting for the monthly sweep). Finds the
  blog/press feeds, registers them in `rss_feeds` under the market's collection
  topic, and picks the pages worth watching.
- **ATS discovery** (careers page → hiring system → open-role counts) — cadence
  ~14 days, needs only the domain.
- **Crunchbase seeding** — vendors without a `crunchbase_url` get one guessed
  from the brand slug, stored `"verified": false`. **Verify it by hand**: a
  wrong slug once marked a live vendor as closed (AquilaI, 31 Aug).
- **Corpus name attribution** — the daily scan starts linking the vendor's name
  in already-collected coverage.

## 3. What stays manual

- **`linkedin_company_url` identifier** — nothing discovers it, and LinkedIn
  headcount tracking (the movers card) is ineligible without it. Find the
  company page, confirm it is the right company (search, not slug-guessing),
  insert with kind `linkedin_company_url`. Format: normalized value without the
  trailing slash, display value with it.
- **`brand_monitoring_enabled`** on the `bw_market_brands` row — a deliberate
  subset (13 of 89 on market 2 before this), not a default. Decide per vendor.
  The routes' bulk toggle also rewrites `brand_keywords`; a vendor created by
  the add route already has good keywords.
- **`social_account` identifier** — comes from a top-voices run, which is paid
  (xpoz + model calls). Never run it for one vendor without asking.
- **`is_public`** — stays false. The public ten is earned-coverage ranked;
  don't hand it out.

## 4. Verify

- Policy rows exist and are eligible:
  `SELECT source, eligible, ineligible_reason FROM bw_entity_source_policies
   WHERE brand_id = :b;`
- After the discovery run: an `rss_feeds` row for the vendor's blog, and the
  vendor page stops saying "Site changes: no monitored pages".
- After the next ATS pass: an `ats_board` identifier and an openings count.
- The vendor's name resolves in the registry:
  `GET /markets/{id}/vendors` shows the identifiers.

## Known gap

The add-vendor route accepts a vendor with no website; everything in §2 is then
ineligible and nothing says so on the spot (the policy row records
"no active domain identifier on file"). Require the domain, or surface the
reason in the response.
