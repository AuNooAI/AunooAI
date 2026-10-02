# Adding a vendor to a market: checklist

This is the checklist for adding one company to a Market Monitor registry, such as market 2
("AI in the SOC", the market behind aisocnews.com). Follow every step. Vendors added by hand
before October 2026 were missing their logo, brand colour, category, funding record and HQ
country, because the add-vendor route creates only the brand, the registry row and a domain,
and nothing reported what was left out.

`scripts/market_add_vendor.py` does steps 3 to 6 from one spec file and then runs the audit.
The audit is the check: a vendor is done when it shows no gaps except a headcount that is
still waiting on its first LinkedIn read.

## 1. Decide whether it belongs

- **Does it sell an AI SOC product?** The registry tracks companies whose product does AI
  security operations work (triage, investigation, response, detection). Platforms next to the
  market (network sensors, sandboxes) and service providers whose AI is a feature of a
  managed service (MDRs) stay out unless Oliver decides otherwise. A large platform company
  with its own AI SOC product (Splunk, Microsoft) goes in as an incumbent (below).
- **Is it a large incumbent?** CrowdStrike, Palo Alto Networks, Splunk (Cisco), Microsoft,
  Google Cloud and Leidos belong in the market, but their headcount and followers are a whole
  company's, tens of times any startup's. Set `"status": "incumbent"` in the spec. The vendor
  is then collected and shown in news like any other, but it is listed beside the maturity
  map under "Large incumbents" rather than placed on it. It is also left out of every size
  figure (headcount, open roles, funding, the market headcount total and trend, and the
  vendor-page benchmarks). It still counts in share of voice and activity. Search for the
  product, not the company (`search_name`: "Charlotte AI", "Cortex XSIAM", "Security
  Copilot"), because a bare "Microsoft" search brings in all of Microsoft's news. To mark an
  existing vendor, use the Horizon tab's "Mark a vendor … incumbent" form.
- **Does it sell under two names?** A vendor can carry several `search_name` identifiers,
  and each becomes a search term. Splunk (Cisco) is searched as both "Splunk" and
  "Cisco XDR". Once a vendor has any search name, its display name is no longer searched,
  so add that too if it should be.
- **Is it a product line of a smaller company?** Add it under the product's name with the
  parent's LinkedIn page, and write an analyst note (`control_note`). HawkEye (DTS Solution)
  is the example.
- **Is it already tracked?** Requests often come from vendors that are already on the page.
  Run the audit for the market and search the output for the name.

Requests arrive in `market_vendor_requests`: `source = 'form'` is a company asking in,
`source = 'top_voices'` is a company we found posting about the market. Nothing marks a request
done; adding the vendor closes it.

## 2. Collect the facts

| Field | Where to get it | Why it matters |
|---|---|---|
| Website | the request, or a search | logo, site pages, blog feed, domain matching |
| LinkedIn company URL | **the site footer**, not a guess | headcount, posts and job counts all read it; without it the vendor is never placed on the map |
| Crunchbase slug | crunchbase.com/organization/&lt;slug&gt; (a guess is fine) | funding rounds, acquisitions |
| X / Bluesky profile | the site footer | social posts are credited to the vendor |
| Keywords | the company name, made specific | which articles are credited to the vendor |
| Search name | only when the name is generic | what the news search looks for |
| Category | "AI Security" / "SOC Automation" for market 2 | grouping on the vendor lists |
| HQ country, founded year | site "About", LinkedIn, Crunchbase | vendor page, geography |
| Funding | the company's own press release first, then trade press | 30% of the map's size axis |
| Brand colour | the logo, or the site's accent colour if the logo is black or white | charts and the vendor dot |

**Keywords and search names for generic names.** A single word that is also an ordinary word or
another product collides: "Blink" matched Amazon's Blink cameras, and "HawkEye" matched the
HawkEye keylogger. Use compound terms only (`BlinkOps`, `DTS HawkEye`, `UpHold Effect`). A
two-word search name is searched as an exact phrase.

**Funding status** is one of `Disclosed` (needs `total_musd`, the sum of all disclosed rounds in
US$ millions), `Undisclosed` or `Bootstrapped`. Only `Disclosed` counts on the map; the others
mean "not measured", never zero. Put a public company or a subsidiary under `Undisclosed` and
say why in the notes. Always give the source links.

## 3. Write the spec file

A spec file is JSON. The format is in the script's docstring; Tracecat's is:

```json
{"market_id": 2,
 "display_name": "Tracecat",
 "website": "https://www.tracecat.com",
 "linkedin_url": "https://www.linkedin.com/company/tracecathq",
 "crunchbase_slug": "tracecat",
 "social": ["https://x.com/tracecathq"],
 "brand_keywords": ["Tracecat"],
 "search_name": null,
 "category": "AI Security", "sub_category": "SOC Automation",
 "hq_country": "United States", "founded_year": 2024,
 "funding": {"status": "Disclosed", "total_musd": 1.5,
             "notes": "$1.5M pre-seed (Dec 2024) from Y Combinator ...",
             "sources": ["https://..."]},
 "colour": {"hex": "#181818", "source": "logo (black)"},
 "control_note": null,
 "provenance": {"via": "top_voices", "request_id": 33}}
```

## 4. Dry run, then apply

```bash
.venv/bin/python scripts/market_add_vendor.py add spec.json           # dry run, rolls back
.venv/bin/python scripts/market_add_vendor.py add spec.json --apply
```

On `--apply` the script:

1. creates the brand and the registry row, with social collection on;
2. sets the keywords, category, HQ, founded year and funding record;
3. adds the domain, website, LinkedIn, Crunchbase, social and search-name identifiers;
4. fetches the logo from the site and sets the colour, fitted so it reads on light and dark
   backgrounds;
5. writes the map status and analyst note, when there are any; an incumbent is also switched
   off for Brand Watcher, whose name checks would match a giant's name in every article;
6. re-syncs the market's search terms, so the vendor is searched for from the next cycle;
7. creates the collection schedule (8 sources; 7 are eligible at first, because job listings
   wait for the careers-page discovery);
8. queues the first paid reads (LinkedIn profile, LinkedIn posts, Crunchbase, about 4 cents),
   so the vendor has a headcount and posts within the hour;
9. runs the audit on the new vendor.

No restart is needed. The front page is cached for 90 seconds.

## 5. Check the next day

```bash
.venv/bin/python scripts/market_add_vendor.py audit --market 2 --brand <id>
```

- **Headcount arrived.** If not, look at the LinkedIn profile run in `bw_collection_runs`. A
  failed run usually means a wrong LinkedIn URL.
- **The vendor's posts were read.** `bw_market_articles` rows for its posts have a
  `review_verdict`.
- **The vendor appears on the page.** aisocnews.com shows a vendor once it has a development or
  a map rating, and a new vendor gets its rating on the next daily map refresh.

## 6. Close the request

If the request came from the form, reply to the sender with the vendor's link on the page. Only
send that email once the vendor actually appears on the page.

## Audit the whole registry

```bash
.venv/bin/python scripts/market_add_vendor.py audit --market 2
```

This lists every collecting vendor with a gap. Set a missing colour with:

```bash
.venv/bin/python scripts/market_add_vendor.py colour --brand <id> --hex '#rrggbb' --source logo --apply
```

Fetch missing logos with `scripts/fetch_vendor_logos.py --market 2 --apply`.
