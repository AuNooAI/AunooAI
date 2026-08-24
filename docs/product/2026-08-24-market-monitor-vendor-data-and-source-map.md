# Market Monitor: vendors stop showing blank rows, and a page that says where each field comes from
_2026-08-24 · Market Monitor (internal tool, bugfixing only — not on any customer site)_

**Audience note.** Market Monitor runs on one internal site and no customer uses it. There is no
customer-facing surface here and nothing in this document should be sent outside the company.
It is written up because the underlying mistake is one we could repeat on a customer product,
and because the new page is worth knowing about if you demo the tool internally.

## What shipped

- Vendors added by hand no longer show an empty row. When we read a company's LinkedIn page we
  now keep the country, founding year and headcount instead of discarding them.
- Intezer and Prophet Security, the two vendors showing nothing, now have real data.
- A new "Data Map" page lists every source we collect from, what each one gives us, and what a
  company needs on file before we can collect it at all.

## Why it matters

**Blank vendor rows had nothing to do with collection failing.** Before: a vendor added through
the "Add vendor" button started with every registry field empty, and nothing ever filled them
in. Only the original spreadsheet import wrote those fields, and it ran once. So a vendor added
afterwards showed dashes forever, and it looked like we were failing to collect on them.

We were collecting fine. Every time we read a company's LinkedIn page we already pulled its
country, founding year and headcount — and then filed it somewhere the vendor table does not
read. Now those readings fill in a blank field automatically. They never overwrite a value
somebody curated, so a good hand-entered number cannot be clobbered by a worse automatic one.
The analyst using the tool feels this: a vendor they add themselves now fills in on its own
after the next read, instead of staying blank and looking broken.

**One vendor could never have been collected at all.** Intezer had no LinkedIn address on file.
We can only collect from a source when we hold the right address for that company, and a company
missing one is skipped silently — no error, no warning, it simply never appears in the results.
Intezer had been sitting in that state. We added the address and ran a full collection to prove
it works. That silent-skip behaviour is deliberate and correct, but until now nothing in the
tool told you it was happening.

**Nowhere said which source fills which field.** Three pages already covered collection: one
says whether a source is working, one says how often it runs, one says how many rows we hold.
None answered the question that actually came up — *where does this number come from, and why
is that column empty?* The new Data Map page answers it in a table, and states three things
that were easy to get wrong:

- Crunchbase gives us funding rounds and investors but **no dollar amounts**. That is why a
  successful Crunchbase read still leaves the funding column blank. It is not a bug.
- PitchBook, ZoomInfo and Indeed are wired up but their field mappings have not been confirmed
  against a real response yet. Treat what they return with suspicion.
- The vendor spreadsheet import was a one-time load. Nothing refreshes it on a schedule.

The operator feels this one. It turns "why is this empty?" from a code-reading exercise into a
page you can look at.

## Release notes (copy-ready)

**Internal only — do not send to customers.**

- Vendors added by hand now fill in their country, founding year and headcount automatically
  from the next LinkedIn read. Curated values are never overwritten.
- Fixed the blank rows for Intezer and Prophet Security.
- Companies LinkedIn lists in two countries now record their headquarters country correctly.
- Fixed three data sources — PitchBook, ZoomInfo and Indeed — that had never worked. Requests
  for them were marked as in progress and then silently never sent, so they hung forever.
- New Data Map page under Collection: every source, what it collects, where it lands, and what
  each company needs on file before that source can run.

## Demo / walkthrough

Market Monitor → **Collection** → **Data Map** (last tab, after Data).

Thirteen rows, one per source. Cost and how often each runs are read live from the schedule, so
if you change an interval in Settings the Data Map reflects it rather than drifting out of date.

To see the fix that sits behind it: **Vendors** → Intezer or Prophet Security. Both were an
unbroken row of dashes this morning.

## Positioning notes

None. This is an internal tool with no customer surface and no competitive story attached to it.

## Limits and what's next

**PitchBook, ZoomInfo and Indeed have now been diagnosed and fixed** — see the release notes
above. Worth knowing what this means in practice: these three had never once worked. Every run
of them since they were added sat marked "running" forever. Nobody noticed because a request
that is never sent produces no error.

They still will not return much yet. We hold no PitchBook or ZoomInfo web address for any
vendor, and both need one entered by hand — there is no way to look them up automatically. Until
somebody enters those addresses, both sources will now finish cleanly and report "no companies
with a usable address" instead of hanging. Only Indeed will actually fetch anything, because it
searches on the company name.

**Two numbers disagree and we left them alone.** LinkedIn says Intezer was founded in 2016; our
research said 2015. LinkedIn reads 90 employees; we have 88 on file. Prophet Security's live
reading matches its row exactly. Nothing decides which source wins when they disagree, because
the rule today is simply "don't overwrite what is already there".

**The registry has now been audited, and it is clean.** Of the 83 vendors we track, none is
missing a country or a headcount, and one is missing a founding year. That one is SOCAI, and it
is not a gap: the original import recorded that SOCAI is a service line of a university research
institute rather than a funded company, and that no founding year could be established. So the
blank-row problem was confined to the two vendors we already fixed. There is no backlog.
