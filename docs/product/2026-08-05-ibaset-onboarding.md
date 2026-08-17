# A competitive-intelligence site for iBASEt, live the same day as the demo call
_2026-08-05 · new customer site (ibaset.aunoo.ai) + a collection-reliability fix on all Brand Watcher sites_

**Audience note.** Internal only. iBASEt is a prospect from a demo call, not a signed
customer, and half their inputs are still marked to-confirm. Nothing here is sendable copy;
it exists so sales and product know what the site can already show and what it cannot.

## What shipped
- A working intelligence site for iBASEt at ibaset.aunoo.ai, built from their written remit:
  their brand plus four confirmed competitors under watch, and four scheduled analyst agents
  that carry the client's own questions — why is Tulip winning aerospace-and-defence MES
  deals, and what are Siemens, SAP and Dassault doing in manufacturing software specifically.
- A fix to article screening on four of the six brand-monitoring sites. Articles the system
  was unsure about are judged by an AI model; on sites cloned from our template, that model
  was not configured, so every unsure article was thrown away without any error showing.

## Why it matters
**For the iBASEt pitch:** the site went from a call transcript to live monitoring in one
working session, with the client's priorities encoded rather than generic defaults. Their
top concern — a small competitor with almost no public footprint — is handled the way they
asked: the bar for keeping an article about Tulip is set deliberately low, because for a
low-volume vendor a single article carries more signal than routine coverage of SAP. The
first test run proved the screening works both ways: it kept the pipeline open for real
Tulip news and correctly threw out ten look-alike articles about the Dutch tulip mania.

**For every existing brand-monitoring customer:** before the fix, a site cloned from our
template silently discarded exactly the articles that needed a second look — the borderline
ones. No error, no gap on any dashboard; the articles simply never arrived. Two sites had
this live, and two more would have inherited it with the next software update. All six are
now verified clean.

## Release notes (internal only)
- New site: ibaset.aunoo.ai — 5 brands, 14 collection keywords, 4 scheduled analyst agents,
  full platform enabled (newsletters, consensus, foresight).
- Fixed: borderline-article screening on sites cloned from the Brand Watcher template
  discarded articles when the judging model was missing from the site's model list. Model
  entries and credentials added on the affected sites and on the template, so future clones
  start correct.
- Fixed: monitoring keywords created through the API were searched as separate words rather
  than exact phrases; the eight multi-word competitor phrases on the new site are now exact.

## Demo / walkthrough
Log in at ibaset.aunoo.ai → Explore → Brand Watcher. The Brands tab shows iBASEt against
Tulip Interfaces, Siemens, SAP and Dassault Systèmes; the Perception tab compares them on
five dimensions including employee sentiment from Glassdoor. Agents tab lists the four
scheduled agents with the client's questions as their instructions. Expect sparse data for
the first days — collection only started today, and Tulip genuinely publishes little.

## Positioning notes
This is the "sole CI analyst at a niche vendor" story: one person feeding a company-wide
weekly newsletter and battlecards, up against three giant competitors and one fast small one.
The remit mapped onto the existing product almost entirely as configuration — the one gap the
prospect asked about that we could not switch on today is coordinated-amplification detection,
which lives in the SaaS stack and is currently switched off for cost.

## Limits and what's next
- Waiting on the client: the remaining ~11 competitors, their customer/prospect list (until
  then there is no trigger-event agent for sales), the delivery channel for alerts (email
  recipients are deliberately empty), and the foresight question for the monthly consensus
  readout.
- The weekly pack grouped by the client's five questions needs a small newsletter-template
  build; the battlecard-formatted output does not exist yet as an artifact.
- The site shares the social-collection API key with other sites; if social volume ramps,
  it needs its own key or requests will start being rate-limited.
- The template still lags canonical code by three weeks; until it is refreshed, every new
  clone needs a manual code resync after provisioning.
