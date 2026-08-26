# Indeed job listings can be collected after all
_2026-08-26 · Market Monitor — hiring_

## What shipped

- Indeed job listings can now be collected and attributed to the right company.
- Each listing is kept only when the employer Indeed reports is the company we searched for.
- Expired listings are dropped rather than counted as open roles.
- The collector stays operator-triggered rather than automatic, and the reason shown on screen now says why honestly.

## Why it matters

**We had written Indeed off, and the reason was wrong.** The stated reason — visible in the collection health panel — was that Indeed listings "cannot be attributed to a specific vendor". That came from one field, `posted_by`, which looks like an employer filter and is not: it accepts a fixed list of poster types and rejects a company name. That part was right.

The conclusion drawn from it was not. Indeed's search field is documented as "search jobs by job title **or company**", and every listing it returns carries the employer's name. So a company's listings can be found and checked — the same way the applicant-tracking-system collector works: search by company, then keep only what actually belongs to that company.

Who feels it: any company hiring through Indeed rather than LinkedIn or its own board. Those listings were invisible, and the product said they were unobtainable.

**The checking half is not a formality.** Because the search matches job titles as well as company names, searching for one company genuinely returns other companies' jobs. The sample record used to test this is a sawmill shift supervisor at Louisiana-Pacific Corporation — a real result, and obviously not one of the security vendors being tracked. A listing is kept only when the employer Indeed reports contains every distinguishing word of the company's name, so "Kenzo Security" accepts "Kenzo Security, Inc." and rejects "Kenzo".

That is deliberately the opposite of the rule used for employer reviews, where a shortened name is sometimes the right match. The difference is who chose the search: when we supply the company name, an answer with fewer of our words in it is the wrong company, not a synonym.

**It stays operator-triggered on purpose, and now the reason is accurate.** Indeed's search requires a location and has no "anywhere" option, so a company hiring across several countries needs a separate paid search for each. That is the reason to run it on request rather than on a schedule — a real cost and latency consideration rather than the capability gap previously claimed.

Cost, for planning: about $2.50 to sweep all 84 companies once at typical volumes, before the per-location multiplier. Each search takes around seven minutes.

## Release notes (copy-ready)

- Indeed job listings can now be collected per company and are attributed by the employer Indeed reports.
- Listings whose employer does not match the company searched for are discarded, and the number discarded is recorded.
- Expired Indeed listings are not counted as open roles.
- Search location is taken from the company's own headquarters where known.
- Indeed collection remains operator-triggered; the collection health panel now explains that this is a cost and location constraint, not a limitation on attributing listings.

## Demo / walkthrough

Market Monitor → SOC Automation → Collection → Sources & Health. The Indeed row now explains its status accurately. Triggering a collection for a single company is done from that company's page.

No Indeed collection has been run yet — the code is in place and tested against the provider's own sample, and the first live run is a spend decision.

## Limits and what's next

**Nothing has been collected yet.** This has been built and tested against the dataset's documented output, not against a live response. The first real run should be one company, checked by hand, before any sweep.

**A location is required for every search.** Where we do not know a company's headquarters — 12 of 82 here — the search falls back to the United States, so listings elsewhere would be missed. A miss shows up as "no listings", never as another company's jobs.

**Indeed carries no company website**, so attribution rests on the employer's name rather than on a domain. That is weaker than the applicant-tracking-system collector, where a board belongs to exactly one company by construction.

**Companies posting to their own board are already covered** by the collector shipped earlier today, which is free. Indeed matters for companies that use neither LinkedIn nor a recognised hiring system.
