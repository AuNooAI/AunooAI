# Hiring data now comes from where companies actually post their jobs
_2026-08-26 · Market Monitor — hiring_

## What shipped

- We now read job listings from each company's own hiring system, not just LinkedIn.
- Distinct open roles across the market went from 91 to 149. Companies with any listing went from 16 to 20.
- Dropzone AI went from 0 open roles to 11 — the number on its own careers page.
- Each listing shows the date the company published it, where its system provides one.
- A role posted to both LinkedIn and the company's own board is counted once, not twice.
- Listings can be filtered by where they came from.

## Why it matters

**Most of these companies do not hire through LinkedIn.** A customer pointed at Dropzone AI: we showed 0 open roles, their careers page listed 11. We checked, and LinkedIn's own page for the company says "There are no jobs right now." Their hiring runs through Greenhouse.

That was not one company. **67 of 83 companies in this market list nothing on LinkedIn.** The hiring column was close to useless for four out of five companies on the page, and worse than useless where a reader took a zero at face value.

Four companies had exactly Dropzone's problem — nothing on LinkedIn, a full board of their own:

| Company | On LinkedIn | On its own board |
|---|---|---|
| Variance | 0 | 11 |
| Dropzone AI | 0 | 11 |
| Method Security | 0 | 7 |
| Wraithwatch | 0 | 6 |

And four more were badly undercounted. Qevlar showed 1 role on LinkedIn and has 15 on its own system.

Who feels it: anyone using hiring as a read on whether a company is growing. "0 open roles" for a company with eleven vacancies is the kind of wrong conclusion that gets repeated in a meeting.

**The obvious fix would not have worked.** We already collect these companies' careers pages, so extracting the jobs from those pages looks like the answer. It isn't. The stored text of Dropzone's careers page contains the words "No items found." and not a single job title, because the page fetches its listings in the browser after it loads. The jobs were never in the page we had.

What works is asking the hiring system directly. Greenhouse, Ashby, Lever, Workable, Teamtailor and others all publish their job boards openly, precisely so job sites can read them. We now read all of them. It is free, where every LinkedIn request is billed, and it is faster: the whole market took 2 seconds.

It is also more precise about *whose* job it is. A board belongs to exactly one company, so a listing from Crogl's board is Crogl's — no name matching involved. That is the problem that made Indeed unusable for us.

**The dates are better too.** Greenhouse and Ashby both say when the company published a role. LinkedIn never told us reliably, so until now "first seen" was the only date we had, and that is when *we* noticed rather than when the company posted. Both are now shown, separately, because they are different facts.

**One role is now counted once.** Four companies post to both LinkedIn and their own board, and nearly every role appeared in both places — 28 of 7ai's 29 LinkedIn roles were also on its own board. Adding the two sources together would have claimed 188 open roles where there are 149. The company's own board wins, because it is the primary source and the one a reader can go and check. The page says how many duplicates it set aside.

## Release notes (copy-ready)

- Job listings are now collected from each company's own hiring system (Greenhouse, Ashby, Lever, Workable, SmartRecruiters, Teamtailor, Recruitee) as well as LinkedIn.
- Distinct open roles across the SOC Automation market rose from 91 to 149, and companies with at least one listing from 16 to 20.
- Roles published to both LinkedIn and a company's own board are counted once. The number set aside is shown.
- Listings now show the company's own publication date where its system provides one, alongside the date we first saw it.
- Listings can be filtered by source.
- The vendor table column is "Open roles" again rather than "Open roles on LinkedIn".

## Demo / walkthrough

Market Monitor → SOC Automation → vendor table → Dropzone AI's **Open roles** figure now reads 11. Click it to see the roles, each with a Source column and the company's own posting date.

The panel states what it set aside: "39 LinkedIn listings were excluded as the same role already published on the company's own board."

## Positioning notes

This came from a customer looking at our page and knowing it was wrong. Worth telling that way round: they found it, we checked it, the answer was that the number was accurate for LinkedIn and misleading as presented, and the fix was to go and get the missing data rather than to re-label the gap.

It also removes a standing objection to hiring as a signal at all. "You only see LinkedIn" was true and was a fair reason to discount the column.

## Limits and what's next

**Four companies publish no listings we can read.** Their careers pages have no job board behind them and no structured listings of any kind — we checked. For those, a zero still means we found nothing to read, and the page says so.

**Two companies' careers pages refuse us.** They return a 403 to an unfamiliar browser, so we cannot detect a board for them.

**A role we cannot see is still invisible.** These are the boards a company publishes openly. A role filled through a recruiter or a private posting will not appear, and no source we have would show it.

**Change tracking needs two collections.** Newly-appeared and no-longer-listed require two successful runs of the same source, so most listings currently say "first observation". That resolves on the next cycle.

**Employer-review matching is still wrong** — every match in this market is a different company with a similar name. Untouched, and it should not be shown or cited.
